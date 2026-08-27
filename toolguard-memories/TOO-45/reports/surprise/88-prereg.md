---
title: 88-prereg
type: note
permalink: toolguard/too-45/reports/surprise/88-prereg
---

# Ticket 88 pre-registration - the deny-with-exception recipe needs a workable example

**Locked 2026-08-21, before implementation.** Ticket authored by me out of ticket 18's fallout, but the substance -- *"curl should generally be an ask anyway, especially since claude can use its builtin WebFetch"* -- is **Arnon's, 2026-08-20**. Ineligible for the blinded series regardless: the ticket body already contains the measured answer (5/5 ordinary invocations permitted, 5/5 dangerous excluded), so there is nothing left to predict about the fix itself.

Recorded for a different reason, below.

## Production files predicted

**Zero.** This is entirely documentation and one skill file. Under the production-only metric Arnon selected, this ticket scores as a **no-production-file ticket** -- which is itself worth having in the series, because the raw file count would have made it look substantial.

## Files predicted

1. `docs/agent-guides.md`
2. `docs/configuration.md`
3. `.claude/skills/toolguard-security-audit/SKILL.md`

## THE FINDING THAT MATTERS HERE - I shipped a doc that contradicts this ticket

Commit **`f816fea`** (today) added a *"Recipe: deny a command with a legitimate exception"* to `docs/agent-guides.md` **built on `curl`** -- with a worked exact-invocation allow for a localhost health check, verified through the sandbox in both directions.

**Ticket 88's decided conclusion is that `curl` is the wrong example**, because neither its safe set nor its dangerous set is enumerable: `-o` writes a file, `-L` redirects anywhere, a second bare URL exfiltrates, all in the same syntax as ordinary use. The ticket's verdict for curl is **`ask`**, and its chosen teaching example is `find`, whose *dangerous* set is closed and enumerable.

**How it happened**: the recipe was written against ticket 18's fallout, landed as part of a docs sweep, and I did not re-read ticket 88 before committing -- I had it filed as "deny-with-exception recipe", a title that reads as *"the recipe is missing"* rather than *"the recipe's example is wrong."* My commit satisfied the title and contradicted the body.

**This is the third instance in this campaign of the same error**: acting on a ticket's *title or shape* rather than its *body*. The other two are logged as "Read ticket amendments, not bodies" and today's `DEFAULT_COMMAND_PAYLOAD_KEY` misread, where I judged an assignment by its form without reading its docstring. Worth carrying into the consolidated report as a named failure mode, because unlike most findings here it is **mine, repeated, and cheap to prevent**: re-read the ticket body immediately before committing anything that claims to address it.

**Not a live defect**: what shipped is a *suboptimal teaching example* that the ticket itself calls an acceptable tradeoff at the ordinary level (point 4), not an unsafe rule. It is queued for correction, not reverted.