---
title: discover_config_files returns every file twice when the project root is the
  home directory
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/54-discover-config-files-double-counts-when-the-project-root-is-home
---

**FIXED in `05f786d` (TOO-45 phase 2).** `discover_config_files` no longer double-counts when the project root is home — see `toolguard/config.py:269`, with a pinned regression test.

# The same `.claude` directory is enumerated as both project and user level

**Found 2026-08-13. A RED test is in the tree. Low severity today, filed so the red test is actionable.**

## The defect

When the project root **is** the home directory, `discover_config_files` enumerates the same `.claude` directory as both the project level and the user level, returning **every file twice** (measured: `total=4, unique=2`).

**This is not an exotic configuration.** `~/.claude` is itself a `STRONG_PROJECT_ANCHOR`, so any working directory under `~` with no nearer marker resolves the project root to `~`.

## Why "once" is the correct expectation

Not an invention of the test: the **live** hierarchy path, `_discover_levels`, collapses the identical layout to a **single `user` level**. So the two discovery paths already disagree about the same filesystem, and the live one is the one whose answer is right.

## Blast radius today: nil

The only live consumer, `_resolve_target_config_path`, returns on the first match, so the duplicate is never observed. **It is a contract defect waiting for a second consumer** — which is precisely the kind that gets found by whoever adds one, at the worst moment.

## Status in the tree

`test_config.test_discover_does_not_double_count_when_the_project_root_is_home` is deliberately RED.

## Context worth keeping with it

`discover_config_files` is **docstring-labelled "Legacy … superseded"** while `permission_migration.py:802` calls it live (imported by value at line 36). Either the label is wrong or the call is. Deciding that answers whether this defect is worth fixing or whether the function should go.