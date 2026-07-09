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

---

## Step 3 -- Leave `~/.toolguard/` in place (do NOT delete it)

**Do not remove `~/.toolguard/` or anything in it.** It holds only non-executable records --
the install journal, the config/settings backups the install and uninstall made, the decision
ledger (`decisions.json`), and `README.txt`. Toolguard no longer runs anything from here, so
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

## Fallback -- no journal available

If there is no usable journal, do a careful best-effort removal, confirming each step:

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
