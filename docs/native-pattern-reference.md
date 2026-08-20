# What `[native]` is supposed to mirror

**Last verified against Claude Code's published documentation: 2026-08-13.**
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

## Known divergences between toolguard and the above

Recorded here because a reader comparing the two needs them in one place. Each is filed as a proposed ticket with a failing test.

| # | native says | toolguard does |
|---|---|---|
| 17 | `Bash(* install)` matches any command **ending with** ` install` | `[native]*id_rsa` does **not** match `cat id_rsa.pub id_rsa`. The matcher takes the **first** occurrence of the final segment and never backtracks, so the end-anchor check tests the wrong occurrence |
| 18 | `Bash(ls *)` enforces a **word boundary** — matches `ls -la`, not `lsof`; and `:*` is equivalent to ` *` | **resolved** — the boundary is enforced on the whole prefix, so `git log:*` no longer matches `git logfoo`. A trailing `*` still crosses spaces, so `Bash(rm FILE:*)` matches `rm FILE /etc/passwd`, exactly as native does |
| 18 | `:*` is recognised **only at the end**; `Bash(git:* push)` treats the colon literally | **not yet measured** |

Leading `VAR=value` assignments are **engine-wide rather than `[native]`-specific**, so they are documented with the matching engine instead of in the table above. Per the quote above, the two policies have the same shape -- restricting rules match past the prefix, granting rules only for known-safe names -- and differ over the list: native's is Claude Code's own and its members are not named in that documentation, while toolguard's is `assignments_looked_past_when_granting` and starts empty. See [Leading environment assignments](permission-patterns.md#leading-environment-assignments). It is mentioned here because a reader comparing toolguard against the quoted documentation will otherwise not find it.

---

## What this file is not

It is not a specification of toolguard's own DEFAULT, GLOB or REGEX pattern types — those are toolguard's own and are documented in [permission-patterns.md](permission-patterns.md). It covers only `[native]`, and only because `[native]` promises to imitate something we do not control.
