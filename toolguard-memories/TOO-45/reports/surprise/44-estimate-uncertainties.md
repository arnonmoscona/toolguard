---
title: 44-estimate-uncertainties
tags:
- TOO-45
- estimate
permalink: toolguard/too-45/reports/surprise/44-estimate-uncertainties
---

# Named uncertainties behind the ticket-44 touch-set prediction

Ordered by how much each one moves the numbers.

## 1. Whether one wrapper ships or three -- the single biggest driver

The ticket lists three fix directions "cheapest first" and then presents all three as a table, which reads like one work item. But it also says direction 3 is "the largest change", and the sequencing section treats the whole thing as a single slot between phase 2 and phase 4. If the implementer takes only the `home()` accessor, production modified drops to roughly 7-9 and test modified to 4-6, and `hook.py` may barely change. If all three ship, my estimate is about right. If direction 3 (an invocation-scoped context object) also ships, the estimate is far too low -- threading a context through the call graph would pull in `permission_resolution.py`, `resolve.py`, `compound.py`, `api.py` and their tests, none of which I predicted, and would push production modified past 25.

**What would settle it:** the coder task spec for this item -- specifically whether it names one wrapper or three, and whether "invocation-scoped context object" appears as in-scope or deferred.

## 2. Whether the stdout writer extends `error_reporter.py` or becomes a new module

The ticket says "extending the existing `error_reporter` pattern", which I read as in-place. But the four inheritance conditions it lists (injected streams, one observable door, an identity handle for an ambient registry, an announcing failure path) describe a distinct object, and a separate `toolguard/io_streams.py` or `stream_writer.py` is an equally defensible reading. If that happens I lose an addition I did not predict and my `error_reporter.py` prediction may still hit only weakly. This is the most likely single source of a missed *added* file.

## 3. Whether `testability.py` is actually created

The ticket argues *against* it as a default destination, then says to keep it in the design as the named destination for leftovers, "expected to be small, possibly empty". A disciplined implementer who finds every wrapper passes the "would you keep it if the suite vanished" test creates nothing -- and by the ticket's own reasoning all three named wrappers pass. I predicted it at medium mostly because the ticket goes out of its way to reserve the name. I think this is close to a coin flip, and it is the prediction I would drop first.

## 4. Which files actually hold the 23 `Path.home()` calls

This is pure inference from module docstrings and line counts. I am reasonably safe on `config.py`, `log_writer.py`, `once_per_store.py` and `env_config.py` because their stated purpose requires a home-anchored path. I am exposed on the install family: `install_provenance.py` and `install_update.py` may resolve everything from `sys.executable`, `shutil.which` and git rather than from home, in which case three of my medium-confidence rows (`install_provenance`, `install_update`, `test_install_provenance`) are false positives. Same exposure on `subagent.py` and `config_divergence.py`, which might receive their paths by injection already.

**What would settle it:** a per-file count of `Path.home()` and `os.environ` occurrences -- the ticket gives the totals (23 across 10 files, 19 across 8) but not the distribution, and the distribution is the whole prediction.

## 5. Whether `tools/` is in scope at all

`toolguard/tools/` is shipped production code and `installer.py` is the second-largest module in the tree, so its ambient reads count toward the measurement. But this refactor is motivated by the hook path, and an implementer could reasonably scope it to the hook-critical modules and leave operator tooling for a follow-up. That single decision moves two production rows and one test row. I leaned toward including `tools/installer.py` and excluding the rest of `tools/`; the opposite split is plausible.

## 6. Whether the tests change at all in this commit

This is the uncertainty most likely to make my *test* count wrong, and it cuts the other way from everything above. Introducing `path_utils.home()` does not break a `patch("pathlib.Path.home")` -- the old patches keep working, because the accessor calls the thing being patched. So the refactor can land green with zero test edits, and the 485 only comes down in a deliberate follow-up sweep. If the implementer treats "retire the patches" as part of the same item, my test count is about right; if they treat introducing the seam as the item and migrating the suite as the next one, test modified could be 2-4. I predicted the former because the ticket's sequencing argument (do this before phase 4 so new tests are not written twice) only pays off if the tests actually move.

## 7. `test_path_utils.py` -- absence inferred from the inventory

There is no `test/unit/test_path_utils.py` in the file list, which is why I predicted it as an addition. But `path_utils` is clearly exercised through `test_config.py`, `test_hierarchical.py` and `test_tools_project_root.py` today, and a new accessor could simply be tested there. If so my only medium-confidence test addition is wrong and one of those three existing files gains an edit I did not name.

## 8. Instrument-boundary items I deliberately excluded

Three categories I believe have a real chance of appearing in the actual touch set but left out to protect precision, flagged here so a miss can be read as instrument error rather than architecture error:

- `tools/architecture_fitness.py` -- the TOO-45 measurement instrument could plausibly gain an "ambient read" check, since this ticket invents exactly the kind of countable property it exists to track. Also `test/unit/test_architecture_fitness.py`.
- `docs/architecture-as-built.md` and other `docs/` files -- the layer-map argument in the ticket is a documentation change as much as a code one.
- The `toolguard-memories/TOO-45/` notes themselves -- if the scoring counts memory and report files as part of the touch set, my counts are low by several files across both categories. I assumed they are excluded.

## 9. What I think I am most likely to be wrong about, in one line

That the change is *concentrated*. I predicted a tight core (hook, path_utils, error_reporter, config) plus a tail of mechanical call-site edits. The plausible alternative is that once someone starts routing home and env through one door, the call-site tail turns out to be the whole job -- twenty small production edits and almost no design work -- in which case my concentration set is right in composition but badly wrong about where the effort went.
