---
title: TOO-19 s1 SessionStart invariant and m3 wrapper false-positive - coder task
  recall
type: note
permalink: toolguard/implementation/too-19-s1-session-start-invariant-and-m3-wrapper-false-positive-coder-task-recall
---

## Task

Repo `/home/arnon/projects/toolguard`, branch `too-19`, ticket TOO-19. Two small fixes from
the 2026-08-02 code review, both selected by Arnon; other findings deliberately left.

Constraints: unittest not pytest, BDD Given/When/Then docstrings, no function-level imports,
docstring on every function/class, stdlib-only runtime. Never bare python (`uv run python`
only). Never edit outside repo. No git write ops. Never write to real `logs/`. Clean up any
`coder-test/` scratch before reporting. May add new tests to `test/unit/`, must NOT modify or
delete existing ones.

## FIX A (m3) -- correctly hardened registration reported as BROKEN

`toolguard/tools/installer.py::_hook_registration_findings` (~line 1966). `interpreter_missing`
computed only when hardened (`-m toolguard.hook` in command), takes `shlex.split(command)[0]`
as the interpreter. For `env -u PYTHONPATH <venv>/bin/python3 -E -P -m toolguard.hook`, token 0
is `env`, so `Path("env").exists()` is False -- correct config reported BROKEN.

Fix: identify interpreter properly.
- Skip a leading wrapper (realistically `env`; `env` takes its own options and `VAR=value`
  assignments before the command).
- Bare command name resolvable on PATH is NOT missing -- use `shutil.which` (stdlib, already
  imported in installer.py) in addition to `Path(...).exists()`.
- Keep simple/readable, no shell parser. If ambiguous, prefer "not missing" over false BROKEN,
  and say so in the docstring.

Tests required: plain console script (non-hardened), `env`-wrapped hardened, unwrapped
hardened, bare name resolvable on PATH, genuinely nonexistent interpreter (must STILL report
missing -- don't disable the check to fix the false positive).

## FIX B (s1) -- document why SessionStart is deliberately unhardened

`cmd_register_hooks` (installer.py ~line 614) hardens PreToolUse but registers SessionStart as
bare `<binary>-session-start`. This is correct/necessary: `_detect_shadow_status`
(`toolguard/session_start.py` ~line 434) compares `governing_package_root()` (via
`install_provenance`) against the checkout root. If SessionStart were hardened (`-E -P -m
toolguard.session_start`-style), it would always resolve the INSTALLED distribution, so shadow
detection could never observe a shadowed working tree -- the feature would silently stop
working with no test failing.

Fix:
1. Comment at the registration site in installer.py (around `session_start_binary = ...` /
   `session_start.append(...)`) stating the invariant and consequence of breaking it.
2. Same point in `technical-notes.md`'s existing "Shadowed-hook detection and install
   hardening (TOO-19)" section -- there's already a paragraph near the end (~line 1137-1144)
   documenting SessionStart is left unhardened, but its rationale is the "except Exception,
   degrades gracefully" one, NOT the shadow-detection-would-break one Arnon named. Need to ADD
   the missing invariant, not just restate the existing text.
3. A test that FAILS if SessionStart is ever hardened -- name it so its purpose is
   unmistakable, failure message must explain WHY hardening SessionStart is wrong (not just
   that it changed).

## Verification required

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -- must be OK. Baseline confirmed **2175** tests, exit 0.
  Count must go UP after the fix.
- `uv run ruff check .` and `uv run ruff format --check .` clean repo-wide.
- `uv run python tools/check_doc_links.py` exits 0.
- Fix A: paste before/after table for all five command shapes.
- Fix B: demonstrate the new guard test FAILS if SessionStart registration is hardened
  (mutate, observe, restore).
- Real repo `logs/` untouched: before/after entry counts. Baseline confirmed: 60 files in
  `/home/arnon/projects/toolguard/logs/` before starting.

## Report location

basic-memory project `toolguard`, path `TOO-19/TOO-19 s1 SessionStart invariant and m3
wrapper false-positive.md`, tagged `task-memory` and `TOO-19`. Include before/after table,
mutation evidence for Fix B's guard, and any command shape judged too ambiguous to classify.

## Key file locations found during investigation

- `toolguard/tools/installer.py`: `_hook_registration_findings` ~1966-2041,
  `cmd_register_hooks` ~614-748, `_hardened_hook_command` ~575-611, `_HOOK_MODULE` ~535.
- `test/unit/test_tools_installer.py`: `TestHardenedHookCommandSpacePathQuoting` (~676-763) is
  the closest existing precedent for `_hook_registration_findings` tests -- plain
  `unittest.TestCase`, no `ConfigIsolationMixin` needed (builds settings.json directly, no
  `toolguard.config` discovery). `TestRegisterHooks` (~770) is the CLI-level class (extends
  `InstallerTestCase`, which patches `Path.home()` itself) where the SessionStart hardening
  guard test belongs -- existing test at line ~773 (`test_user_scope_writes_settings_json`)
  already implicitly checks the bare form via `assertIn`, but doesn't explain why or fail with
  a clear message.
- `toolguard/session_start.py`: `ShadowStatus` ~397-431, `_detect_shadow_status` ~434-473.
- `technical-notes.md`: "Shadowed-hook detection and install hardening (TOO-19)" section
  starts at line 991; SessionStart-unhardened paragraph at ~1137-1144.

## Plan status

Plan understood from the prompt directly (already detailed/actionable); proceeding without an
extra approval round-trip per "avoid over-asking on small phases" auto-memory guidance, since
the task came pre-specified with exact function/file targets, required tests, and verification
steps. Will flag deviations in the report.
