# Uninstalling toolguard with an AI agent (guided)

**Audience: an AI agent (Claude) a user has asked to remove toolguard.** This reverses what
the guided install ([install.md](install.md)) set up, reliably, from the record it kept -- so
the user never has to reverse-engineer what changed. Be calm and thorough: a user reaching for
uninstall may be frustrated, and a clean, complete rollback is the point.

## Principles

- **The journal is the source of truth.** `~/.toolguard/install-journal.md` records every
  action the install took and its exact reverse. Undo those reverses in REVERSE order (last
  action first).
- **Consent per step, and re-confirm shared things.** Confirm before each undo. For anything
  the install flagged as possibly shared (e.g. uv), re-confirm explicitly -- the user may have
  started relying on it.
- **Keep `~/.toolguard/`.** Its contents are non-executable records (install journal, config
  backups, decision ledger, a `README.txt`). Uninstall does NOT delete them -- they exist for
  auditability and problem resolution, and a frustrated user especially should not lose the
  record of what was done. See Step 3.
- **Keep the logs by default.** Toolguard's decision logs (`logs/toolguard-*.md` under each
  governed project, plus the conflict/session streams) are the single best artifact for
  debugging a problem after the fact -- exactly what a user would send the author. Do NOT delete
  them as part of a routine uninstall; recommend keeping them and only remove them if the user
  explicitly asks (see Step 3). Distinguish *your own* install/probe logs from pre-existing ones.
- **Back up before you delete/restore**, so an uninstall is itself recoverable.
- **Verify at the end** that toolguard no longer governs.

---

## Step 1 -- Read the journal

Open `~/.toolguard/install-journal.md`. It lists numbered entries, each with an `action` and a
concrete `reverse`. Build the ordered list of reverses (highest order index first). Show the
user a short plain-English summary of what will be undone, in order, before doing anything.

**If the journal is missing or incomplete** (e.g. toolguard was installed some other way, or
by hand), fall back to a best-effort manual uninstall -- see "Fallback" below -- and tell the
user it is best-effort because there is no recorded history.

**Note on backup filenames -- do not guess which one to restore.** `~/.toolguard/backups/`
commonly holds *several* backups of the same original file: each mutating install action makes
its own (e.g. `toolguard_hook.toml` is typically backed up more than once, once per Phase 4/10
step that edited it). If two backups of the same file happen to land in the same wall-clock
second, the second one gets a `-2`, `-3`, ... suffix instead of overwriting the first (e.g.
`toolguard_hook.2026-07-11-125502.toml`, then `toolguard_hook.2026-07-11-125502-2.toml`) -- the
suffix means "another backup, same second," not an ordering or ranking. **Always restore the
exact path named in that entry's `backup:` field -- never infer which file to use by listing the
directory or picking the newest-looking name.** With several same-named candidates for one
original file, a guess can silently restore the wrong point in its history.

---

## Step 2 -- Replay the reverses, in reverse order

Work top-down through the reverses (most recent action undone first). The typical order:

1. **Installed skills** -- remove `~/.claude/skills/toolguard-security-audit/` and
   `~/.claude/skills/toolguard-maintenance/` if the install put them there.
2. **Config files** -- delete the `toolguard_hook.toml` files the install wrote (or restore a
   prior version if the journal recorded one). Do the same for any migrated
   `settings.local.json` if the user wants the migration reverted (restore the migration
   backups the migrate script created) -- ask, since they may want to keep those rules.
3. **Hook registration** -- restore the `settings.json` / `settings.local.json` backups the
   install made (this removes exactly the hooks it added). Confirm the hooks are gone.
4. **The toolguard tool** -- `uv tool uninstall toolguard` (or the matching command for
   whatever manager the journal records: pipx/pip/venv/user-dictated).
5. **uv itself** -- ONLY if the journal says this process installed it, and ONLY after fresh
   confirmation, since the user may now use uv for other work.

For each: confirm, back up if you are overwriting/restoring, perform the recorded reverse, and
note completion. If a reverse action does not apply cleanly (a file already changed by the
user since install), stop and explain rather than forcing it.

**Never execute a recorded reverse that deletes or empties `~/.toolguard/` itself, even if a
journal entry says to.** Step 3 below is the permanent policy and overrides any individual
entry -- a buggy or hand-written entry (e.g. one mistakenly attached to `init-state`) may say
otherwise. If you find one, skip just that part of the reverse, tell the user their journal
contains a stale/incorrect entry, and proceed with the rest of the rollback normally.

---

## Step 3 -- Leave `~/.toolguard/` in place (do NOT delete it)

**Do not remove `~/.toolguard/` or anything in it.** It holds only non-executable records --
the install journal, the config/settings backups the install and uninstall made, the decision
ledger (`decisions.json`), any captured crash reports in `errors/` (see Step 5), and
`README.txt`. Toolguard no longer runs anything from here, so
keeping it costs nothing and preserves a full, auditable history of what was installed and
removed -- invaluable if the user hit problems (the reason they may be uninstalling) or later
wants to reinstall or understand what happened.

**Tell the user explicitly, at the end, that you left it:** state that `~/.toolguard/` was kept
on purpose for auditability and problem resolution, that it contains nothing executable, where
it is, and that they are free to delete it by hand at any time (`rm -rf ~/.toolguard`) if they
want it gone -- that is their call, not something uninstall does for them. `README.txt` in the
directory says the same.

(If you want a clean marker, you may append a final "uninstalled" entry to the journal noting
what was removed and when -- but never delete or rewrite earlier entries.)

**Do not conflate "clear my memories / clean slate" with wiping `~/.toolguard`.** A request to
reset agent *memory*, start fresh, or "prep a clean slate for testing" is about the AGENT's
notes -- it is NOT permission to delete `~/.toolguard/` (the journal, backups, ledger, README).
Those are the user's audit trail and are exactly what you would need if a re-test goes wrong.
Even when explicitly prepping for another test run, **leave `~/.toolguard/` intact unless the
user names that directory specifically and says to delete it.** If a "clean slate" request is
ambiguous, ask before removing anything under `~/.toolguard/`. (An install started later does
not blindly "continue from" an old journal anyway -- it reads it and reconciles.)

---

## Step 3b -- Keep the logs (do NOT delete them by default)

Toolguard writes decision logs to `logs/toolguard-YYYY-MM-DD.md` (plus conflict and session
streams) under each governed project's root. These are the most useful artifact for diagnosing
whatever went wrong -- and the thing a user would send to the toolguard author. **A routine
uninstall should keep them.**

- **Default: keep the logs.** Do not delete them as part of teardown. Tell the user where they
  are and that you left them on purpose for debugging.
- **Only remove logs the user explicitly wants gone**, and be precise about *which*: if this
  install/attempt created its own logs (e.g. under a temp probe dir, or a fresh `logs/` you made
  today), you may offer to remove just those, but leave any pre-existing logs untouched unless
  the user says otherwise. When unsure whether a log predates your work, keep it and ask.

---

## Step 4 -- Verify

Confirm toolguard no longer governs:

- `command -v toolguard` no longer resolves (if the tool was uninstalled), and
- the hook entries are gone from the relevant `settings.json` / `settings.local.json`, and
- a new Claude Code session no longer routes tools through toolguard (no toolguard decisions in
  the logs; if takeover was on, commands are once again handled by Claude's native
  permissions).

Report what was removed and what (if anything) was intentionally kept.

---

## Step 5 -- Offer a trace dump, and an issue report if toolguard misbehaved

A user reaching uninstall often hit a problem, so this matters here even more than at install.
Follow **[install.md](install.md#phase-t----trace-dump-and-issue-reporting-offer-this) Phase T**:

- **Offer a session-trace dump** (Phase T.1) built from the transcript -- the environment,
  timeline, verbatim allow/deny/warning strings, the reproduction, and the final state. Together
  with the kept logs (Step 3b) and the journal, this is a complete record. **Check
  `~/.toolguard/errors/` and quote any crash reports there in full** -- a user reaching for
  uninstall often hit exactly the kind of unexpected exception this directory captures.
- **If the trouble looks like a toolguard defect** (not the environment or an agent mistake),
  **offer to file a GitHub issue** on the user's behalf (Phase T.2): search existing issues
  first, show the user any that match, ask whether it is the same or new, and open one only with
  their explicit go-ahead -- attaching the summary and the trace dump.

---

## Fallback -- no journal available

If there is no usable journal, do a careful best-effort removal, confirming each step. **If you
need to restore from `~/.toolguard/backups/` without a journal entry pointing at the exact file,
do not guess.** A single original file (e.g. `settings.json`) may have several backups from
different points in time, including same-second collisions disambiguated with a `-2`, `-3`, ...
suffix (see the note in Step 1) -- list every candidate for that filename's stem, sorted by their
embedded timestamp, and show the **full list** to the user so they pick the right one, rather
than silently restoring "the newest" or "the first one found."

1. `uv tool uninstall toolguard` (or check `pipx list` / `pip show toolguard` / a project
   `.venv` for how it was installed).
2. Remove the toolguard `PreToolUse` matchers and the `toolguard-session-start` `SessionStart`
   hook from `~/.claude/settings.json` and any project `.claude/settings.local.json` (back up
   first).
3. Delete `toolguard_hook.toml` at the user level (`~/.claude/`) and in any projects that have
   one, if the user wants toolguard fully gone.
4. Remove `~/.claude/skills/toolguard-*` if present.
5. Leave `~/.toolguard/` in place (Step 3) -- even in a best-effort teardown, keep the records;
   tell the user it is there and that they can delete it by hand if they want.

Tell the user this path is best-effort because there was no recorded install history, and that
a future guided install would keep one.
