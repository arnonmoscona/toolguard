# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.
General guidelines that apply to all projects are in `~/.claude/CLAUDE.md`, which is
loaded automatically by Claude Code before this file.

## Project overview

The toolguard project is primarily a Claude Code hook for better management of permissions
than what is provided out of the box. It can be used in other ways as well. The main tools
it governs are `Bash`, `Read`, `Write`, `Edit` with the most attention devoted to `Bash`.
Toolguard provides extended syntax to support a richer expression of permission rules.
Specifically, it allows configuring permissions in the native Claude syntax (as a drop-in
replacement to the native configuration), but also supports regular expression command
matching and glob expression command matching (glob is natively supported for Read, Write,
and Edit -- but not for Bash).

The functionality of the tool is documented in detail in the project's [README](README.md).

## Architecture and design constraints

The tool is designed to have minimal runtime dependencies, so that execution only requires
the Python standard library. We add dependencies only when absolutely necessary.

For development we have one major dependency: the `canopy` parser generator. In order to
parse the bash commands Claude issues and match them against rules, one must break compound
commands into parts and evaluate each part separately -- otherwise the permission rules
become complex and brittle. Parsing with pure-Python regular expressions is crude,
error-prone, and extremely difficult to reason about and debug. Therefore **we avoid doing
any custom parsing of bash commands and instead rely on a formal PEG grammar for all
parsing**. From the formal grammar file (`toolguard/parser/bash_parser.peg`) we generate a
Python base parser using `canopy` (must be installed on the development system) and this
parser is used by `command_extractor.py` to break compound commands into parts. Note that
the grammar is not a full bash grammar -- it is only intended for the sole purpose of
breaking up compound commands from patterns often used by Claude Code. Canopy creates no
runtime dependencies as the generated Python code depends only on the standard library.

## Ticket tracking

Tickets for this project are prefixed by `TOO-`. Example: `TOO-123`.

To read a ticket:

```bash
~/projects/youtrack_api/get-issue.sh "TOO-123"
```

## Memory management

Use the basic-memory MCP server with `project='toolguard'` for all notes in this project.
See the global memory management guidelines (loaded via `~/.claude/common-memory.md`).

When creating memories in the context of a specific ticket, add the ticket ID as a tag
(e.g., `TOO-14`).

## Technical notes

Additional project-specific notes can be found in [technical-notes.md](technical-notes.md),
if the file exists.
