---
title: TOO-17 Grammar-First Rework Task Recall
type: note
permalink: toolguard/implementation/too-17-grammar-first-rework-task-recall
tags:
- TOO-17
- task-memory
- coder-state
---

# TOO-17 Grammar-First Rework Task Recall

## Task
Rework the multi-line Bash bypass fix (TOO-17) to be GRAMMAR-FIRST.

## Problem with Previous Attempt
The previous agent added `toolguard/parser/multiline.py` (~1,186 lines) with:
- Hand-written quote-aware state machine for statement splitting
- Regex-based control structure recognition (_SIMPLE_FOR_RE, _SIMPLE_WHILE_RE, _SIMPLE_IF_RE)
- This violates the core project constraint: "we avoid doing any custom parsing of bash
  commands and instead rely on a formal PEG grammar for ALL parsing"

## Hard Constraint
ALL structural parsing (splitting statements, pipes, control structures, quoting) MUST go 
through the PEG grammar (`bash_parser.peg` -> regenerated `bash_parser.py` via canopy).

## What Must Be Done
1. Extend `bash_parser.peg` to handle multi-line commands:
   - Newline as statement separator at top level
   - Allow newlines after binary operators (&&/||/|) for continuation  
   - Quoted strings MUST span newlines (`.` matches `\n` inside quotes)
   - Recognize control structures for/while/until/if/case (both `;` and NL-delimited bodies)
   - Recognize `[ ]`, `[[ ]]`, `(( ))` constructs
   - Process substitution `<(...)`, `>(...)`
   - `<bash-family> -c <quoted>` detection
2. Regenerate `bash_parser.py` using: `cd toolguard/parser && npx -y canopy@latest bash_parser.peg --lang python`
3. Format with: `uv run ruff format toolguard/parser/bash_parser.py`
4. Extend `command_extractor.py` to walk new grammar nodes
5. Replace `multiline.py` structural parsing with grammar-based extraction
6. Keep ONLY the narrow lexical pre-pass: CRLF->LF, backslash join, heredoc body
   extraction/removal, # comment stripping, whitespace collapse

## What STAYS in pre-pass (sanctioned non-grammar steps)
1. CRLF/CR -> LF
2. Backslash-continuation join (remove `\`+LF except inside single quotes)
3. HEREDOC body extraction/removal (PEG can't back-reference delimiter)
4. `#` comment stripping at word boundaries outside quotes
5. Whitespace collapse/trim

## Test spec
File: `test/unit/test_multiline_bash.py` - 23 tests (DO NOT MODIFY)
Run: `uv run python -m unittest test.unit.test_multiline_bash`

## Key Fixtures
- F1-F6: Multi-line bypass (denied)
- F7: Quoted sep not split
- F8-F9: Comments / # in args
- F10: Backslash continuation
- F11: uv python -c multiline -> ask
- F12: heredoc->python -> ask 
- F13: cat<<EOF|pbcopy -> allow (body not parsed)
- F14: cat<<EOF|bash -> deny (body decomposed as bash)
- F15: tee /etc/passwd <<EOF -> normal sentinel matching
- F16: bash -c "git status; rm -rf /" -> deny (inner decomposed)
- F17: python3 -c "..." -> ask
- F18: cat|python3 -c "...|echo x" -> ask
- F19: for f in a b; do echo $f; grep $f g; done -> allow
- F20: if grep -q foo f; then cp a b; rm t; fi -> (per cp/rm rules)
- F21: if [ -f f ]; then cat f; fi -> allow
- F22: while..if..else..fi..done (complex nested) -> ask
- F23: diff <(sort a) <(sort b) -> ask
- F24: unparseable -> ask (or deny)
- Plus 2 new "newline_body" loop tests (23rd and 24th in the file)

## Canopy Regeneration Command
```
cd /home/arnon/projects/toolguard/toolguard/parser && npx -y canopy@latest bash_parser.peg --lang python
```
Then: `cd /home/arnon/projects/toolguard && uv run ruff format toolguard/parser/bash_parser.py`

## Definition of Done
1. All 23 tests in test_multiline_bash green
2. Full test suite green WITH and WITHOUT CLAUDE_SETTINGS_PATH
3. Ruff format + check: clean
4. No structural parsing in multiline.py (only narrow pre-pass)
5. Grammar does all structural work
