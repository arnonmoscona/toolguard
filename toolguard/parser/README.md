# Toolguard Bash Parser

This directory contains the bash command parser for toolguard, used to parse compound bash commands for security permission checking.

## Architecture

The parser is built using **Canopy**, a PEG (Parsing Expression Grammar) parser generator. The authoritative source is the PEG grammar file `bash_parser.peg`, which is compiled into Python code by Canopy.

### Files

- **`bash_parser.peg`** - The authoritative PEG grammar defining bash command syntax
- **`bash_parser.py`** - Generated Python parser (DO NOT EDIT DIRECTLY - see regeneration instructions below)
- **`command_extractor.py`** - High-level command extraction API with fallback regex parsing
- **`__init__.py`** - Package initialization

## Grammar Coverage

The PEG grammar handles:

- **Compound commands**: Commands connected by control operators
  - `&&` (AND operator) - Execute second command if first succeeds
  - `||` (OR operator) - Execute second command if first fails
  - `;` (semicolon) - Sequential execution
  - `&` (background) - Background execution

- **Pipelines**: Commands connected by `|` (pipe operator)

- **Simple commands**: Individual commands with redirections and substitutions

- **Redirections**: File I/O operations
  - `>` (output redirect)
  - `>>` (append redirect)
  - `<` (input redirect)
  - `<<` (here-document)
  - `2>` (stderr redirect)
  - `2>&1` (stderr to stdout merge)
  - `n>&m` / `n<&m` (file descriptor redirects)

- **Command substitution**:
  - `$(command)` - Modern substitution syntax
  - `` `command` `` - Backtick substitution

- **Quoting**:
  - Single quotes `'...'` - Literal strings
  - Double quotes `"..."` - Variable expansion allowed
  - Dollar quotes `$'...'` - ANSI-C quoting
  - Escape sequences with `\`

- **Variable references**: `$VAR`, `${VAR}`, `${VAR:-default}`, etc.

- **Reserved words**: `if`, `then`, `else`, `elif`, `fi`, `case`, `for`, `while`, `do`, `done`, etc.

## Usage

### High-Level API (Recommended)

Use `command_extractor.py` for most use cases. It provides robust error handling with automatic fallback:

```python
from toolguard.parser.command_extractor import extract_commands

# Extract individual commands from a compound command line
commands = extract_commands('git status && rm -rf /')
# Returns: ['git status', 'rm -rf /']

commands = extract_commands('cat file | grep pattern')
# Returns: ['cat file', 'grep pattern']
```

The `extract_commands()` function:
1. Attempts to parse using the Canopy PEG parser
2. Falls back to regex-based splitting if parsing fails
3. Returns a list of individual command strings

### Low-Level API

Direct access to the Canopy parser:

```python
from toolguard.parser import bash_parser

try:
    tree = bash_parser.parse('git status && rm file')
    # Walk the tree to extract information
except bash_parser.ParseError as e:
    # Handle parse errors
    print(f"Parse failed: {e}")
```

For backward compatibility, there's also:

```python
from toolguard.parser.bash_parser import parse_command_line

commands = parse_command_line('git status && rm file')
# Returns: ['git status', 'rm file']
```

## Regenerating the Parser

If you modify `bash_parser.peg`, you must regenerate the Python parser:

```bash
cd toolguard/parser
canopy bash_parser.peg --lang python
```

**IMPORTANT**: After regeneration, you must manually re-add the `parse_command_line()` wrapper function at the end of `bash_parser.py`. The wrapper is marked with comments indicating it was added manually.

### Installing Canopy

Canopy is a JavaScript tool. Install it globally with:

```bash
npm install -g canopy
```

Or use it with npx:

```bash
npx canopy bash_parser.peg --lang python
```

## Interface with Hook Code

The parser integrates with the toolguard permission checking system via:

1. **`extract_commands()`** - Main entry point used by `compound.py`
2. **Tree walking** - The Canopy parser returns a parse tree that can be walked to extract specific information
3. **Fallback handling** - If parsing fails, regex-based extraction provides a safety net

The hook code in `hook.py` uses this to:
- Extract individual commands from compound command lines
- Check each command against allow/deny patterns
- Apply "strictest policy wins" logic across all commands

## Maintenance Guidelines

### When to Modify the Grammar

Modify `bash_parser.peg` when you need to:
- Support new bash syntax features
- Improve parsing accuracy
- Add support for bash constructs not currently handled
- Fix parsing bugs in complex command structures

### When NOT to Modify the Grammar

Don't modify the grammar for:
- Simple regex patterns - use `command_extractor.py` fallback instead
- Python-specific logic - put it in `command_extractor.py`
- Permission checking logic - that belongs in `compound.py`

### Testing After Changes

Always run the full test suite after making changes:

```bash
uv run pytest toolguard/test/unit/ -v
```

Key tests to verify:
- `test_compound.py` - Tests bash parser and command extraction
- All parser tests should pass
- Edge cases with quotes, operators, and special characters

### Code Style

- Generated code (`bash_parser.py`) follows Canopy's style - don't reformat
- Custom wrappers in `bash_parser.py` follow project style (120 chars, single quotes)
- `command_extractor.py` follows standard project conventions

## Known Limitations

1. **Not a Full Bash Parser**: This parser handles the subset of bash syntax needed for security permission checking. It does not parse:
   - Complex control structures (if/else/case/for/while loops) - only reserved words
   - Function definitions
   - Arithmetic expansion `$(( ))`
   - Process substitution `<( )` and `>( )`
   - Array operations
   - Brace expansion `{a,b,c}`

2. **Fallback Limitations**: The regex fallback doesn't respect quotes, so in rare parse failure cases, quoted strings containing operators may be incorrectly split.

3. **Error Messages**: Parse errors can be verbose. The high-level API catches these and falls back gracefully.

## Design Decisions

### Why Canopy?

- **Grammar as Source of Truth**: The PEG grammar serves as documentation and implementation
- **Maintainability**: Easier to extend than hand-written recursive descent parser
- **Correctness**: PEG parsers are deterministic and easier to reason about
- **Testing**: Grammar rules are explicit and testable

### Why Keep Fallback Regex?

- **Robustness**: If the parser fails on unusual input, we still get reasonable results
- **Security**: Permission checking should err on the side of caution, not fail open
- **Graceful Degradation**: Better to over-warn than under-protect

### Why Simple Commands Only?

For permission checking, we only need to identify individual commands (e.g., `git status`, `rm file`). We don't need to understand the full semantics of control flow or conditional execution. The security policy is applied uniformly to all commands in a compound line.

## Future Enhancements

Potential improvements:

1. **Context-Aware Extraction**: Extract file paths from redirections and arguments
2. **Variable Expansion**: Resolve simple variable references for better matching
3. **Semantic Analysis**: Understand control flow to give more precise permission advice
4. **Better Error Messages**: Provide actionable feedback when parsing fails

## References

- [Canopy Documentation](https://canopy.jcoglan.com/)
- [PEG Parsing](https://en.wikipedia.org/wiki/Parsing_expression_grammar)
- [Bash Reference Manual](https://www.gnu.org/software/bash/manual/bash.html)
