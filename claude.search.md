# Efficiently searching in code

## Quick decision rule

Before searching, ask: **am I looking for a symbol or for text?**

| Question                                                                                                                                                            | Use |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|---|
| Where is `Foo` / `bar()` defined?                                                                                                                                   | `mcp__jetbrains__search_symbol` |
| Who calls it / what does it call? (call graph)                                                                                                                      | `mcp__jetbrains__analyze_calls` |
| What's its signature?                                                                                                                                               | `mcp__jetbrains__get_symbol_info` |
| A string literal, template fragment, comment, log message, config value                                                                                             | `ag` |
| Anything in gitignored / generated / just-created files the IDE hasn't indexed (index updates usually are no more than a few seconds unless changes are very large) | `ag` |
| Logical combinations (`--and`/`--not`) over text                                                                                                                    | `ag` piped into `grep -v` (or `ack`'s `--not`) |
| The IDE is not running / no MCP available                                                                                                                           | `ag`, falling back to the recipes below |

Semantic queries via the MCP are precise, return structured metadata (so a follow-up `Read` is usually unneeded), and are immune to the blind spots of text-based recipes listed further down. Use them by default for anything symbol-shaped.

## Why this matters

The default search tools that Claude uses, like `grep` and similar tools, can end up using a lot of context, as claude has to sift through a lot of output, often reading whole files in order to narrow down the search and find the material it is looking for.

This system has an installation of `ag` (silver searcher), which is a fork of `ack`, which is also on this system. You may find further documentation of ack by running `ag --help` or for more details read [the ack docs](https://beyondgrep.com/documentation/). Note that while `ag` is much faster than `ack` - it does not have every single command line option that `ack` has. Notably, it does not support `--and`, `--or`, and `--not`.

Importantly, ack allows you to narrow down searches by file type, `--and`, `--or`, `--not`. When you combine this with the knowledge that the project has consistent formatting (with `ruff`). You can very efficiently search for material with very
little impact on the context buffer.

*(The following examples are from the flowers project. Substitute your own project directory and module paths.)*

For example, suppose you want to know where the function `get_state()` is defined. You could infer this from a Python module that uses it that is already in your context, but assuming you don't have it, you could do something like `ag --python 'def get_state\(' flowers/`. For something more complex, how about finding all the probable places that this function is used, knowing that I do not use wildcard imports in the project. You can use `ag -l --python 'from flowers.app.state.state_store import(?=[\s\S]{0,1000} get_state)' flowers/ | xargs ag --python '\bget_state\('` - which is reasonably accurate under the file formatting rules of the project. **Use `\bget_state\(` not ` get_state\(`** — the word boundary catches both ` get_state(` and `module.get_state(`, whereas a leading literal space silently misses attribute-style calls. (For this specific kind of search prefer `mcp__jetbrains__analyze_calls` when available — it's semantic, so it also catches aliased imports and same-named-symbol false positives that text patterns can't reason about.)

If for instance you wanted to do the same search but exclude lines that have `State.LOGIN_STATE`, the easiest way with `ag` is to pipe to `grep -v`: `ag -l --python 'from flowers.app.state.state_store import(?=[\s\S]{0,1000} get_state)' flowers/ | xargs ag --python '\bget_state\(' | grep -v 'State.LOGIN_STATE'`. (`ack` has a native `--not` flag if you prefer that style: `... | xargs ack '\bget_state\(' --not 'State.LOGIN_STATE'`.)

Granted, there may be other ways to do the same, but I have not observed you trying those. So whenever reasonable use this and other techniques to save on space in the context buffer or the need to write elaborate inline python to perform complex code searches.

# Searching using JetBrains MCP tools

When you are running in a JetBrains IDE, you can use the included MCP tools (`mcp__jetbrains__*`), which expose the IDE's semantic index. The tools you'll use most:

* `search_symbol` (`mcp__jetbrains__search_symbol`) — locate a class/function/method/variable definition by name; returns location and signature information.
* `analyze_calls` (`mcp__jetbrains__analyze_calls`) — analyze the call graph for a symbol: who calls it and what it calls. Note this focuses on function calls; it does not enumerate all reference kinds such as imports or attribute access.
* `get_symbol_info` (`mcp__jetbrains__get_symbol_info`) — get detailed information about a symbol at a known file location.

## Canonical workflow for "who calls Foo?"

1. `search_symbol(name="Foo", ...)` (`mcp__jetbrains__search_symbol`) — returns one or more matches with file location.
2. `analyze_calls(...)` (`mcp__jetbrains__analyze_calls`) — given the symbol location, returns its call graph (callers and callees).

Notes for next time:

* Add filters to `search_symbol` when you know the kind or language — disambiguates fast and avoids returning every same-named symbol across all supported languages.
* `search_symbol` may return multiple matches (overloads, same name across modules). Pick the right one before proceeding.

## When to prefer which

* **Symbol-anchored questions** — "where is it defined", "who calls it", "what's its signature" — prefer the JetBrains MCP tools. They are precise, give richer per-result metadata (so you usually don't need a follow-up `Read`), and avoid the structural blind spots of text-based recipes.
* **Text-anchored questions** — string literals, comments, TODOs, HTML/template fragments, configuration values, log messages, regex patterns, files outside the IDE's index (gitignored / generated / very recently created), or anything you want to combine with `--and` / `--not` / `--or` — prefer `ag` / `ack`. The MCP cannot do these.
* **Mixed** — start with the MCP for the symbol, then use `ag` to scan for related non-code traces (e.g. "is this state name also baked into a template or a session key string?").

## Structural blind spots in text-based recipes

The clever `ag` recipes earlier in this document work for the specific examples shown, but be aware of what they can miss compared to semantic tools like `mcp__jetbrains__analyze_calls`:

* A pattern like ` get_state\(` with a leading space won't match `module.get_state(...)` attribute-style access.
* Pre-filtering by `from … import` misses files that use `import some.module` followed by attribute access.
* Aliased imports (`from … import get_state as gs`) are invisible to text patterns keyed on the original name.
* A second unrelated symbol of the same name elsewhere in the project will produce false positives.
* The import line itself is typically excluded by these recipes.

*(From the flowers project, for illustration:)* For `get_state` in that codebase, the `ag` recipe and the semantic tool agreed on the call sites — but the semantic tool additionally found the import lines, and remained correct when aliased imports or refactors were introduced.

## Caveats when using the MCP

* The IDE must be running and the project indexed. Fresh checkouts or just-edited files may lag for a moment.
* `analyze_calls` focuses on function calls; for broader reference tracking (imports, subclass declarations), inspect the file context manually or fall back to `ag`.
* Occasionally a `filePath` in a result comes back as a bare/short path missing the project prefix. Canonicalise against the `filePath` you passed in if you need stable absolute paths.
* Sometimes the IDE can be misconfigured and its index may include many files that are not in the project source - especially python or javascript package files that I do not want indexed by the IDE (they are extremely expensive and mostly not relevant). So:
    * if you find that the MCP tools return results that are outside the project's source directories then it is probably misconfigured and you should let me know about this. This can happen when I upgrade python, change the IDE project configuration or misconfigure indexing options for specific directories. It happens sometimes but not often.
    * **How to detect:** scan every result's `filePath`. The result is suspect (and worth flagging) if either:
        1. it falls outside the project root entirely (i.e. doesn't start with the project's directory), or
        2. it sits under any directory matching `.venv*` (e.g. `.venv`, `.venv-py312`).

      Both conditions indicate the index is pulling in files that should be excluded — not a tool bug, but a configuration drift to surface.
    * If you want to do searches specifically outside of the project's source directories, or perhaps on unindexed files in the project's directory then you can fall back on the command line tools.
