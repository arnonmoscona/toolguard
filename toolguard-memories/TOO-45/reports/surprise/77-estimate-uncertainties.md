---
title: 77-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/77-estimate-uncertainties
tags:
- TOO-45
- surprise-measurement
- blinded-estimate
---

# Named uncertainties -- ticket 77 estimate

Ordered by how much they move the predicted set.

## 1. How many places actually match a command against a rule (largest single risk)

I predicted `permissions.py`, `compound.py`, `permission_resolution.py` and `resolve.py` as four separate touches because their one-line docstrings suggest four separate concerns, and because TOO-45's punch list has been *removing* cycles between exactly this group -- which usually means they still talk to each other a lot. If the matching call was already funnelled to one function, three of those four drop out and my production count is overstated by roughly a fifth. If instead `compound.py` (1102 lines) keeps its own leaf-matching path, my count is right for the wrong reason: the change would be duplicated, and that duplication is itself the finding.

**What would settle it:** one look at whether `compound.py` calls into `permissions.py` for each leaf, or re-implements the match.

## 2. Whether the grammar has to move

This is the highest-variance item and the only one with a procedural multiplier. Detecting a leading `NAME=value` is bash parsing, and the project rule is unambiguous that bash parsing lives in `bash_parser.peg`, with a mandatory two-phase change procedure. But the ticket says the assignment "reaches the leaf command verbatim", which is equally consistent with the grammar *already* tokenising it correctly and only the consumer discarding the distinction.

- If the grammar already models it: `.peg` and the 6536-line generated parser both drop out, `command_extractor.py` becomes a small read of an existing field, and `test_bash_parser.py` drops out. Minus 3 files.
- If it does not: `.peg` + regenerated parser + extractor + model + parser tests, and the work splits across two reviewed commits, which may show up as two touch sets rather than one.

I split the difference at `medium`, which means I am guaranteed to be somewhat wrong in one direction. The *worst* outcome for the codebase -- and the one I would bet on if forced -- is that the strip gets hand-rolled in Python because it looks like a two-line string operation, which is the exact failure mode `.claude/rules/bash-grammar.md` exists to prevent.

## 3. Where the safe-list default lives, and whether it is configuration at all

I put the default names in `constants.py` and the loading in `config.py`/`config_types.py`/`config_validation.py` -- four files for one list. Plausible alternatives that would cut that:

- The safe-list is a hardcoded constant with no config key at all (the brief says "configured", so I discount this, but "configured" could mean "configured in the source table" as `self_integrity.py` and `recommended_protections.py` apparently are).
- It lands in `env_config.py`. I deliberately excluded that module: its docstring says it governs toolguard's *own* environment configuration, whereas this list is about env assignments appearing in *governed commands*. If the implementer read the module name rather than the docstring, it goes there instead -- a name-collision error I would find more interesting than my miss.
- `config_validation.py` is only 139 lines and may not be the place per-key validation actually happens; validation may be inline in `config.py`.

## 4. Whether "additional variant alongside the raw one" is a matcher change or a data-shape change

Two implementations with very different touch sets:

- **Matcher-side:** the match function tries raw, then stripped. Contained, few files, but every caller that matches must be found.
- **Data-side:** the extracted leaf command carries both spellings, and matching is unchanged. Wider in the parser, narrower in the engine -- and much better for the "prose is output, not a data structure" rule this project cares about, since the stripped form is *derived data* that should be carried rather than re-derived at each match site.

I leaned matcher-side in the file list but data-side in confidence for `command_model.py`, which is an inconsistency I am aware of and could not resolve without reading.

## 5. Logging and audit surface -- likely my biggest recall gap

I named no logging file, and I am uneasy about it. This project has a measured, documented incident (TOO-45, the compound-allow under-logging) about exactly this: a decision changes shape, the structured detail is not carried to the writer, and the audit log silently loses fidelity. If a decision can now be reached *via a stripped variant*, the log arguably must record which spelling matched -- otherwise the audit trail cannot distinguish "denied `rm`" from "denied `FOO=1 rm` after stripping". That would pull in `log_writer.py`, possibly `error_reporter.py`, and `test_log_writer.py` / `test_logging_streams.py`.

I left them out because the brief's design statement says nothing about reporting, and precision is scored. If the touch set contains them, my omission is an *architecture* miss on my side, not instrument error -- I applied the ticket's frame instead of the project's own lesson.

## 6. Tooling that reasons about allow rules

Excluded on purpose, and flagged so a hit is interpretable rather than surprising:

- `tools/danger.py` and `tools/security_audit.py` -- a safe-list is a new way to widen an allow rule, so a static risk finding for a badly chosen entry (`LD_PRELOAD`, `PYTHONPATH`) is defensible. `tools/environment_audit.py` already reports `PYTHONPATH` shadowing, which makes the adjacency real.
- `tools/mining.py` -- the ticket explicitly fences this off as ticket 75. I trust the fence; if `mining.py` appears anyway, the two tickets were merged in implementation.
- `tools/replay.py` / `test/verdict_corpus/` -- a change to deny matching changes replayed verdicts by construction. If the corpus contains any fixture with an env prefix, fixture data moves. I could not check, and fixture data may not count as a module touch.

## 7. Scope creep from the ticket's own paragraph on wrappers

The ticket names `timeout`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob` and bare `xargs` as behaving identically, and notes native strips all three normalisations. The brief scoped the decision to env assignments only. If the implementer treated the three normalisations as one feature -- which is how the native documentation frames them -- the parser and matcher touches grow substantially and a wrapper table appears somewhere new. I estimated for env assignments alone.

## What I am most likely to be wrong about, in one line each

- **Overstated:** the four-way split of matching across `permissions`/`compound`/`resolve`/`permission_resolution`, and the four-file config plumbing for a single list.
- **Understated:** logging/audit fidelity, and the possibility that this is implemented as one normalisation feature rather than one bug fix.
- **Coin-flip:** the grammar. Everything downstream of `.peg` is contingent on a question I was not allowed to check.
