---
title: TOO-45 phase 2 unit 1 follow-up - coder report
type: note
permalink: toolguard/too-45/too-45-phase-2-unit-1-follow-up-coder-report
tags:
- task-memory
- TOO-45
---

# Unit 1 follow-up — the three consequences of the prefix-boundary fix

## Outcome table

| Job | Target | Outcome |
|---|---|---|
| 1 | `test_tools_consolidate` — 6 reds across 3 locations | **GREEN** |
| 1 | `test_tools_maintenance` — 2 reds pinning the same emitted regex | **NEEDS A DECISION** (fifth location; I stopped as instructed) |
| 2 | `test_tools_uninstall_readiness::test_a_path_scoped_rule_does_not_admit_a_second_unrelated_path` (10 subtests) | **GREEN** |
| 3 | `test_self_integrity::test_a_prefix_token_or_absolute_path_does_not_escape_the_patterns` (3 subtests) | **GREEN** |

## Verification numbers

- Full suite: **3628 tests, 82 failures + 1 error**. Baseline was 109 unique red IDs; now **82**.
- **Newly red vs baseline: 2.** Both are the `test_tools_maintenance` pins I am not licensed to edit. Nothing else.
- **Newly green vs baseline: 29** (many belong to the concurrent units, not to me).
- `uv run ruff format .` — clean, 175 files unchanged.
- `uv run ruff check .` — **1 error, not mine**: `F401 typing.Optional imported but unused` in `toolguard/tools/annotate.py`, a file another agent owns and which I am forbidden to touch.

A transient third newly-red, `test_tools_rule_apply.TestApplyToml.test_refused_write_propagates_and_reports_unwritten`, appeared in my mid-run and was gone by the final run. It patches `toolguard.tools.rule_apply.verified_write_config`; `rule_apply.py` was modified at 09:23 by a concurrent agent. Not mine, and self-resolved.

## Job 1 — every test line I changed, before and after

### `test/unit/test_tools_consolidate.py`

**Location 1 — `TestFamily1GitHappyPath::test_consolidation_preserves_prefix_extension_commands`** (name kept deliberately, so the ID Arnon named stays greppable and the verification-by-ID holds).

Docstring, before:
```
Then prefix-extension commands such as 'git difftool' and
     'git diffstat HEAD' keep verdict 'allow' -- the consolidation does
     NOT silently tighten what the DEFAULT cmd:* prefix already allowed.
```
after:
```
Then prefix-extension commands such as 'git difftool' and
     'git diff-index HEAD' -- which glue a suffix onto a pattern's final
     token -- decide the SAME either way. Consolidation must be verdict
     preserving; which verdict that is belongs to the DEFAULT cmd:*
     prefix semantics, not to this test.
```
Body, before:
```python
self.assertEqual(
    decide(config_b, "Bash", cmd).decision,
    "allow",
    f"{cmd!r} should remain allowed after consolidation",
)
```
after:
```python
with self.subTest(command=cmd):
    self.assertEqual(
        decide(config_b, "Bash", cmd).decision,
        decide(config, "Bash", cmd).decision,
        f"consolidation changed the verdict for {cmd!r}",
    )
```
*Why*: the test's value is that consolidation is verdict-preserving; pinning the literal `allow` pinned a verdict that only ever held because of the defect. Measured: all three commands are `ask` before and `ask` after. `subTest` added so a single failing command names itself.

**Location 3 — `TestFamily1EquivalenceAndLandmine::test_deny_guarded_landmine_survives_consolidation`**, two lines.

Before: `self.assertEqual(p.added_pattern, "[regex]^uv run alembic (downgrade|upgrade)")`
After: `self.assertEqual(p.added_pattern, r"[regex]^uv run alembic (downgrade|upgrade)(?=\s|$)")`
*Why*: the emitted literal now carries the token-boundary lookahead.

Before: `"uv run alembic downgradex": "allow",`
After: `"uv run alembic downgradex": "ask",`
*Why*: `uv run alembic downgrade:*` never matched `...downgradex` under correct semantics. Measured `ask` for BOTH the original and consolidated config, so the test's real claim — the two configs agree — is untouched. Docstring updated in the same edit.

**Location 2 — `TestFamily2MkdirSubsumption._make_mkdir_config`**, re-based, class NOT deleted.

Before: `allow=["mkdir -p /tmp/:*", "mkdir -p /tmp/claude-code:*"]`
After: `allow=["mkdir -p:*", "mkdir -p /tmp/claude-code:*"]`
*Why*: **a genuinely-true subsumption fixture exists**, so the class still tests family-2 subsumption rather than being gutted. Measured: `mkdir -p:*` matches `mkdir -p /tmp/claude-code`, `mkdir -p /tmp/claude-code --x` and `mkdir -p`; `propose_consolidations` emits exactly one `static-subsumption` proposal removing `mkdir -p /tmp/claude-code:*` with `added_pattern=None`, and `0 broadened` with the corpus. All four tests pass unchanged apart from the fixture and their Given lines. Helper docstring extended to say why a `/` boundary will not serve.

**Nothing else in that file was touched.**

### `test/unit/test_tools_installer.py`

**Location 4 — `_EXPECTED_SELF_INTEGRITY_PATTERNS` (line 1159)**
Before:
```python
r"Bash([regex]^rm\b.*\.toolguard)",
r"Bash([regex]^find\b.*\.toolguard.*-delete)",
```
after:
```python
r"Bash([regex](^|[\s/])rm\b.*\.toolguard)",
r"Bash([regex](^|[\s/])find\b.*\.toolguard.*-delete)",
```
*Why*: the pin Job 3 was blocked on; updated to the corrected regexes. Its anti-vacuity purpose is unchanged.

**A THIRD self-integrity pin in the same file that the brief did not mention — line 1363**
Before: `self.assertEqual(decision.matched_rule, r"[regex]^rm\b.*\.toolguard")`
After: `self.assertEqual(decision.matched_rule, r"[regex](^|[\s/])rm\b.*\.toolguard")`
*Why*: same category, same file, same blocker — it asserts the seeded rm rule is the one that matched. Treated as part of location 4 rather than a new location.

**One more line, forced by Job 2 — line 1268 in `test_uninstall_readiness_rules_are_scope_aware_for_project_scope`**
Before: `self.assertIn(f"rm {project_claude_dir / 'toolguard_hook.toml'}:*", text)`
After: `self.assertIn(f"rm {project_claude_dir / 'toolguard_hook.toml'}", text)`
*Why*: **this contradicts the brief's claim that Option A needs no test edit.** The seeded pattern no longer ends in `:*`, so the substring cannot match. The test's stated intent is scope-awareness — that the seeded rule names the PROJECT's `.claude`, not `~/.claude` — and the `:*` carried no scope information, so dropping it preserves the intent exactly. The `:*`-vs-exact behaviour is pinned by `test_a_path_scoped_rule_does_not_admit_a_second_unrelated_path`, which is one of the tests this change turns green, so nothing is left unguarded.

## Job 2 — Option A, re-measured

Applied: `:*` dropped from the five multi-token Bash entries in `toolguard/tools/uninstall_readiness.py` (`uv tool uninstall toolguard`, `rm <hook_toml>`, `rm <hook_local_toml>`, `rm -rf <audit skill dir>`, `rm -rf <maintenance skill dir>`).

Re-measured through `toolguard.api.decide` before relying on the summary:

- **All 8 real-flow probes stay `allow`**, each with `matched_rule` equal to its own pattern — confirmed end to end with the whole seeded table installed together, not just rule-by-rule.
- **All 10 dangerous witnesses become `ask`** (`<probe> /etc/passwd`, `<probe> /home/x/projects` for each of the five).
- Suffixed targets (`<probe>-BACKUP`) were already `ask` under both forms.

**Two corrections to the brief's cost statement.** It said the cost is that `rm -rf <dir> -f` *and* `rm -rf <dir>/` fall to `ask`:

1. `rm -rf <dir> -f` — correct, that is a real new cost of Option A.
2. `rm -rf <dir>/` — **already `ask` before Option A.** The trailing-slash case is a consequence of the prefix-boundary fix, not of Option A, so it should not be counted against this decision.

## Job 3 — the self-integrity anchor

`toolguard/tools/self_integrity.py`, both patterns:

```python
pattern=r"Bash([regex](^|[\s/])rm\b.*\.toolguard)"
pattern=r"Bash([regex](^|[\s/])find\b.*\.toolguard.*-delete)"
```

`[\s/]` rather than `\b` because `\b` holds after `-` and would drag in `docker run --rm`. Verified `sudo rm`, `/bin/rm`, `sudo find ... -delete` are now hard-denied; `ls ~/.toolguard`, `cat ~/.toolguard/README.txt`, `rmdir ~/.toolguard/backups`, `rm -rf /tmp/scratch`, `find ~/.toolguard -type f` and `find /tmp/scratch -delete` are all unaffected.

**Unplanned bonus, and it matters given the measurement below**: because the anchor now accepts a preceding space, the self-integrity hard_deny also catches `FOO=1 rm -rf ~/.toolguard`, `TG_ATTEST_READONLY=1 rm -rf ~/.toolguard` and `timeout 5 rm -rf ~/.toolguard` — all measured `deny`. The env-var escape described below does NOT apply to these two patterns.

## The extra measurement: leading env-var assignments and wrappers

**Measured, not fixed, as instructed.** `extract_commands` carries the assignment into the leaf verbatim; nothing is stripped anywhere:

```
'FOO=1 ls -la'                    -> ['FOO=1 ls -la']
'TG_INTENT=1 ls -la'              -> ['TG_INTENT=1 ls -la']
'timeout 5 ls -la'                -> ['timeout 5 ls -la']
'FOO=1 ls && BAR=2 rm -rf /tmp/x' -> ['FOO=1 ls', 'BAR=2 rm -rf /tmp/x']
```

Consequences, measured separately for allow and deny:

**ALLOW** (config: `Bash(ls:*)`, `Bash(uv run python:*)`) — every prefixed form MISSES its rule and falls to `ask`:

| command | verdict | rule |
|---|---|---|
| `ls -la` | allow | `ls:*` |
| `FOO=1 ls -la` | **ask** | None |
| `TG_INTENT=1 ls -la` | **ask** | None |
| `TG_ATTEST_READONLY=1 uv run python tmp/x.py` | **ask** | None |
| `timeout 5 ls -la` / `nohup` / `nice` / `command` / `builtin` / `noglob` / `stdbuf` / `time` / `xargs ls` | **ask** | None |

**DENY** (config: allow `Bash(*)`, deny `Bash(rm:*)`) — a one-token prefix DEFEATS the deny rule:

| command | verdict | rule |
|---|---|---|
| `rm -rf /tmp/x` | deny | `rm:*` |
| `FOO=1 rm -rf /tmp/x` | **allow** | `*` |
| `TG_ATTEST_READONLY=1 rm -rf /tmp/x` | **allow** | `*` |
| `timeout 5 rm -rf /tmp/x` | **allow** | `*` |
| `nohup rm -rf /tmp/x` | **allow** | `*` |

Two distinct problems, and they deserve separate treatment in whatever ticket this becomes:

1. **The allow-side divergence is the one Arnon predicted**, and it is worse than a nuisance: this project *mandates* `TG_INTENT=1` / `TG_ATTEST_READONLY=1` on exactly the commands where an agent has done the right thing. Disclosure currently costs you your allow rule and sends the command to `ask`. That is a direct incentive against complying with CLAUDE.md.
2. **The deny-side hole is security-relevant and is NOT what the docs describe.** The docs say stripping is applied for allow rules *only* — presumably so a prefix cannot be used to reach a broader allow. Here, an ordinary (non-hard) deny is evaded by prepending any assignment or wrapper. Note the asymmetry: naive "strip for allow only" would fix problem 1 and leave problem 2 exactly as it is. Both `hard_deny` self-integrity patterns happen to be immune after Job 3, but that is a property of those two regexes, not of the engine.

I did not fix either. Wrapper stripping (`timeout`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, `xargs`) is unimplemented in the same way and has the same two-sided shape.

## The one thing I stopped on

`test_tools_maintenance.py` lines 543 and 745 pin `["[regex]^git (diff|log|status)"]`, now emitted as `["[regex]^git (diff|log|status)(?=\s|$)"]`. Same category as location 3, different file — a **fifth location**, so I stopped as instructed rather than edit it. The exact change is appending `(?=\s|$)` inside each expected string; it is a data pin, not an assertion of behaviour, and updating it weakens nothing. These are the only two newly-red tests remaining.

## Errors found in the brief

1. **"no test edit is needed" for Option A is wrong** — `test_tools_installer.py:1268` pins the `:*` form. Detailed above.
2. **The Option A cost is overstated** — `rm -rf <dir>/` was already `ask` before Option A; only `rm -rf <dir> -f` is a new cost.
3. **The self-integrity pin is not just the constant at 1159** — there is a third verbatim pin at line 1363 in the same file.
4. Location 3's category ("any test pinning the emitted regex literal") spans two files, not one; hence the stop above.

## Production defects noticed and NOT fixed

- **Two stale test docstrings I am not licensed to touch.** `test_self_integrity.py:265-269` still says *"RED until the ^ anchor in both patterns is relaxed… All three resolve to 'ask' today"* — now false, the test is green. `test_tools_uninstall_readiness.py:311-320` (`TestUninstallReadinessOverGrant` class docstring) still says *"Proposed ticket 18 is the fix; these tests assert the intended behaviour and are expected RED until it lands"* — both its tests are now green, and as the previous agent noted, ticket 18 was never the fix for half of them. Both need a one-paragraph rewrite.
- **`match_command` still has no direct matcher-level test of the token boundary.** Carried over from the previous report and still true; every guard reaches it through `decide()`. A few `match_command("git logfoo", ["git log:*"])` assertions in `test_permissions.py` remain the cheapest durable protection for the fix this whole unit rests on.
- **The env-var / wrapper stripping gap above**, in both directions.

## Files changed

Production:
- `toolguard/tools/self_integrity.py` — both hard_deny anchors relaxed; module docstring and the rm rationale corrected (the docstring previously stated `sudo rm` and `/bin/rm` match neither pattern, which the fix makes false).
- `toolguard/tools/uninstall_readiness.py` — `:*` dropped from the five multi-token entries; module docstring bullet rewritten (it described the over-grant as a `match_command` defect).
- `toolguard/tools/consolidate.py` — **docstrings only, no behaviour change**: the module docstring's family-2 summary and `_static_prefix_of`'s contract both still claimed a `/` boundary makes the wider pattern cover the narrower one. `_static_prefix_of`'s behaviour is deliberately unchanged — `test_static_prefix_of` pins the `/` acceptance and `test_probe_gate_rejects_unsound_path_boundary_subsumption` pins the probe gate catching it.

Tests (all inside the granted licence except where flagged above):
- `test/unit/test_tools_consolidate.py` — 3 locations.
- `test/unit/test_tools_installer.py` — 3 lines (two self-integrity pins, one Option A consequence).

## Process note against myself

One Bash command in this run went out undisclosed: a `sed -i` fixing an import in my own scratch probe (`scratchpad/measure2.py`). Authored shell, case 4, exactly the category CLAUDE.md names as the one that gets missed. It wrote only to the scratchpad, outside the project. Recording it because the rule says a miss is a miss regardless of blast radius.

## Rollback

Pre-change copies of all four files are in `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/backup/`. Every file I touched can be restored exactly.
