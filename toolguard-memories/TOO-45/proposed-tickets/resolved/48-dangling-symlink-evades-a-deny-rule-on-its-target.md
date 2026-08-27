---
title: A dangling symlink evades a deny rule written against its target, and writing
  through it creates the target
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/48-dangling-symlink-evades-a-deny-rule-on-its-target
---

**FIXED in `05f786d` (TOO-45 phase 2).** A dangling symlink can no longer evade a deny written against its target, including the "strictly worse sibling" case — see `toolguard/normalization.py:16-28,85-91`.

# Dangling symlinks are not canonicalised, so a deny on the target does not fire

**Found 2026-08-13. A RED test is in the tree, and the fix is confirmed by mutating toward it.**

## The defect

`normalize_path` resolves a symlink **only when `path_obj.exists()`** — and `exists()` follows the link. A link whose target does not exist yet therefore keeps its own spelling and is never canonicalised to the target a deny rule names.

Measured, same config, same command shape:

```
cp payload.txt <dangling link>   ->  allow   rule='cp *'
cp payload.txt <live link>       ->  deny    rule='cp * /…/already_there.toml'
cp payload.txt <target path>     ->  deny    rule='cp * /…/not_yet_there.toml'
```

The two control cases run **first and pass**, so the fixture is proven capable of producing a deny.

## Why it is exploitable rather than merely wrong

**`cp`, `>` and `tee` through a dangling link CREATE the target.** So the bypass applies to exactly the files a deny rule most wants to protect *before they exist*:

- a rules file under `~/.toolguard/rules/` that has not been created yet
- a `settings.local.json` that is not there yet
- any not-yet-present config a rule was written to guard in advance

A deny protecting a file that does not exist yet is the case where the protection matters most, and it is the case that does not hold.

## A STRICTLY WORSE SIBLING, found 2026-08-13 in `test_normalization.py` — no dangling link needed

`<dirlink>/f.txt` **never resolves to** `<realdir>/f.txt`. A deny written against the real path does not fire for the same file spelled through a **symlinked parent directory**.

This needs no dangling link and no precondition of any kind — just a symlink anywhere in the path's ancestry. It is the same defect one level up, and it is far easier to hit: `~/.claude` and `~/bin` are symlinks on this very machine.

**Red test:** `test_normalization.test_normalize_path_under_a_symlinked_directory_agrees_with_the_real_path`.

**Fix and its blast radius, both measured.** Resolving when the path **or any parent** is a symlink turns both symlink reds green with zero collateral inside `test_normalization.py`. But the blast radius is real and repo-wide: it moves *every* path under *every* symlinked directory, and this machine's `~/.claude` and `~/bin` are symlinks. **This is a decision, not an obvious repair** — unlike the dangling-link fix below, which is narrow.

Sequence them: the narrow fix first, the parent-resolution question separately and deliberately.

## Fix direction, confirmed

Drop the existence gate — resolve on `path_obj.is_symlink()` rather than on `exists()`:

**Measured: that change turns the module green (0 failures) and breaks nothing else in the suite.**

## Status in the tree

`test_symlink_hierarchy.test_a_dangling_symlink_does_not_evade_a_deny_rule_on_its_target` is deliberately RED, with two passing control assertions ahead of it so a fixture failure cannot be mistaken for the defect.

## The check-to-use race is now pinned, for the first time

`resolve.py`'s docstring has always described a check-to-use race — matching reads live filesystem state, so what is matched may not be what executes. **Nothing in the suite exercised it; it existed only as prose.**

`test_repointing_the_symlink_changes_the_verdict_for_the_same_command` now demonstrates the observable half: the **same command string**, against the **same `Configuration` object**, returns `deny` and then `allow` after the link is repointed. Written as characterisation, and its docstring says so — it records the race rather than claiming it is acceptable.

## A separate defect found in the same pass

**A project `.claude` symlinked onto `~/.claude` erases the user level entirely.** `_discover_levels._add` de-duplicates by resolved path, so `~/.claude` is dropped from `level_dirs`; `user_specificity` then points at a directory that is not in the list, and **no discovered file is labelled `user`**. The user's own config is read at project specificity 0.

This is consistent with the documented rule that attribution follows where a file was *found* — but any consumer branching on `level == "user"` sees nothing, and a user who symlinks their config that way loses the distinction silently. Reported, not asserted red, because which behaviour is correct is a product decision.

## Fixture hygiene note — determinism, NOT a security issue

Before repair, this module's fixture placed the project *beside* the patched home, so the upward walk ran past the temp root into `/tmp/.claude` and `/.claude`. Neither exists on this machine, which is why it never fired. The fixture now terminates every walk inside itself.

**Correction, Arnon 2026-08-13: I first wrote this up as a shared-machine test-integrity hole. That framing was overstated.** A shared development machine is an extreme edge case here — no forks, very low GitHub traffic, no evidence of anyone else developing on it. The real and sufficient reason to fix it is **determinism**: a test that reads state from outside its own fixture can pass or fail for reasons unrelated to the code, and this campaign has already found two modules doing exactly that (`test_auto_migrate`, `test_config_divergence`) with real consequences. That argument stands on its own and does not need a threat model.

Worth keeping as a general note: **reaching for the security framing when the hygiene argument was already sufficient inflates a finding.** The correction cost nothing here, but the habit would erode the credibility of the findings that genuinely are security defects — of which this ticket's main subject is one.