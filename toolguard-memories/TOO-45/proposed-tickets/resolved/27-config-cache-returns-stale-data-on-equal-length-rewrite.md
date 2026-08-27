---
title: The config cache returns stale data after an equal-length, same-mtime rewrite
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/27-config-cache-returns-stale-data-on-equal-length-rewrite
---

**FIXED in `05f786d` (TOO-45 phase 2).** The config cache key now includes a sha256 of the file bytes, so an equal-length, same-mtime rewrite no longer returns stale data — see `toolguard/config.py:176-186`.

# The config cache returns stale data after an equal-length, same-mtime rewrite

## The defect

The config cache keys on `(path, format, st_mtime_ns, st_size)`. A rewrite that changes **content** without changing **length or mtime** collides with the cached entry, and the second read returns the old data.

Constructed and confirmed:

```
["Bash"]  ->  ["Read"]      both 26 bytes, mtime restored
second read returns ['Bash']
```

## Reachability, stated honestly

Narrow in the hook: toolguard is **one process per tool call**, so a cache that lives for one decision cannot go stale within its own lifetime. That bounds the blast radius and is the reason this is not filed as severe.

It is **not** narrow in the tools. `--apply` and `--annotate` are long-lived read-modify-write callers, and read-modify-write is exactly the operation that produces equal-length rewrites: swapping one tool name for another of the same length, flipping a decision word, editing a pattern in place. A tool that reads, rewrites, and reads again within one process can act on the pre-write state.

`mtime` is not the safety net it looks like either. `st_mtime_ns` has nanosecond resolution on paper, but a rewrite that restores mtime (any backup-and-restore, any `shutil.copy2`, any editor preserving timestamps) defeats it deliberately, and coarse filesystem timestamp granularity can defeat it accidentally.

## How it was found

Through a **test docstring**, not through the code. The docstring claimed a same-mtime rewrite still invalidates the cache. It does not -- the test passes only because its fixture happens to grow from 26 to 79 bytes, so the `st_size` component of the key changes. Take the size change away and the claim fails.

That is worth recording as method as much as defect: the false sentence was in a test, the passing test was the evidence for the sentence, and the fixture's incidental size change was doing the work everyone credited to mtime.

## Fix direction

Options, cheapest first:

1. **Add a content hash to the key.** Correct, and the cost is one hash per read of a file already being read.
2. **Drop `st_mtime_ns` and `st_size` for a hash outright** -- simpler key, same guarantee.
3. **Invalidate explicitly on write** in the read-modify-write tools. Narrower, and relies on every future caller remembering.

Option 1 or 2. Option 3 is the shape that produced this.

## Test obligation

The constructed case above: write, cache, rewrite to equal length with mtime restored, read again, assert the new content. It fails today.

## Provenance

Found in the `test/` tier of the TOO-45 #07 sweep, through a test docstring's claim rather than through the cache code. Recorded in the #07 work queue.
