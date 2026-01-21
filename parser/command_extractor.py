"""
Command extraction module for bash compound commands.

This module provides functionality to extract individual commands
from compound bash command lines for security permission checking.

Uses the Canopy-generated PEG parser to walk the AST tree.
All extraction is done via pure tree walking - NO Python string parsing.
"""

import logging
from typing import List, Set

from toolguard.parser import bash_parser

logger = logging.getLogger(__name__)


def extract_commands(command_line: str) -> List[str]:
    """
    Extract individual commands from a compound bash command line.

    This function handles command lines with operators:
    - && (AND operator)
    - || (OR operator)
    - ; (semicolon separator)
    - | (pipe operator)

    It also extracts commands from nested constructs:
    - Command substitutions: $(...) and backticks
    - Subshells: (...)
    - Brace groups: { ...; }

    The function uses the Canopy PEG parser to parse the command line
    and walks the AST tree to extract all commands. All parsing is done
    by the PEG parser - this function only walks the tree.

    Args:
        command_line: The bash command line to parse

    Returns:
        List of individual command strings

    Examples:
        extract_commands('git status && rm -rf /')
        ['git status', 'rm -rf /']

        extract_commands('cat file | grep pattern')
        ['cat file', 'grep pattern']

        extract_commands('command1; command2; command3')
        ['command1', 'command2', 'command3']

        extract_commands('test -f file && cat file || echo not found')
        ['test -f file', 'cat file', 'echo not found']

        extract_commands('echo $(rm -rf /)')
        ['echo $(rm -rf /)', 'rm -rf /']

        extract_commands('(cd /tmp && rm file)')
        ['(cd /tmp && rm file)', 'cd /tmp && rm file', 'cd /tmp', 'rm file']
    """
    if not command_line or not command_line.strip():
        return []

    try:
        tree = bash_parser.parse(command_line)
        return _extract_from_tree(tree)
    except bash_parser.ParseError as e:
        # Parser failed - log and return original command as safety net
        logger.warning(f'Parse failed for command: {command_line[:100]} - {e}')
        return [command_line.strip()] if command_line.strip() else []
    except Exception as e:
        # Unexpected error - log and return original
        logger.error(f'Unexpected error parsing command: {e}')
        return [command_line.strip()] if command_line.strip() else []


def _extract_from_tree(node, include_wrappers: bool = True) -> List[str]:
    """
    Extract commands from the parse tree by walking it.

    This function walks the Canopy parse tree and extracts individual
    commands. It handles:
    - Simple commands (single executable)
    - Subshells: both wrapper (e.g., "(cmd)") and inner commands
    - Brace groups: both wrapper (e.g., "{ cmd; }") and inner commands
    - Command substitutions: both wrapper (e.g., "$(cmd)") and inner commands

    The tree walking is PURE - it only examines node types and attributes.
    NO string parsing is performed.

    Args:
        node: The parse tree node to walk
        include_wrappers: If True, include subshell/brace group wrapper text in results

    Returns:
        List of command strings extracted from the tree
    """
    commands: List[str] = []
    # Track seen command texts to avoid duplicates
    seen_texts: Set[str] = set()

    def add_command(text: str) -> None:
        """Add a command if not already seen."""
        text = text.strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            commands.append(text)

    def extract_from_compound(compound_node) -> None:
        """
        Extract commands from a compound_command node.

        A compound_command contains pipelines connected by control operators.
        We need to find all pipeline_elements and extract their commands.
        """
        if compound_node is None:
            return

        # Get the first pipeline via .pipeline attribute
        if hasattr(compound_node, 'pipeline') and compound_node.pipeline is not None:
            extract_from_pipeline(compound_node.pipeline)

        # Also walk elements to find additional pipelines (after control operators)
        if hasattr(compound_node, 'elements') and compound_node.elements:
            for elem in compound_node.elements:
                # Elements may contain pipelines (after && || ; etc)
                if hasattr(elem, 'pipeline') and elem.pipeline is not None:
                    extract_from_pipeline(elem.pipeline)
                # Recurse into elements that might have nested pipelines
                if hasattr(elem, 'elements') and elem.elements:
                    for subelem in elem.elements:
                        if hasattr(subelem, 'pipeline') and subelem.pipeline is not None:
                            extract_from_pipeline(subelem.pipeline)

    def extract_from_pipeline(pipeline_node) -> None:
        """
        Extract commands from a pipeline node.

        A pipeline contains pipeline_elements connected by pipes.
        """
        if pipeline_node is None:
            return

        # Get the first pipeline_element
        if hasattr(pipeline_node, 'pipeline_element') and pipeline_node.pipeline_element is not None:
            extract_from_pipeline_element(pipeline_node.pipeline_element)

        # Walk elements recursively to find additional pipeline_elements (after pipes)
        def find_pipeline_elements(node) -> None:
            if node is None:
                return
            if hasattr(node, 'pipeline_element') and node.pipeline_element is not None:
                extract_from_pipeline_element(node.pipeline_element)
            if hasattr(node, 'elements') and node.elements:
                for elem in node.elements:
                    find_pipeline_elements(elem)

        if hasattr(pipeline_node, 'elements') and pipeline_node.elements:
            for elem in pipeline_node.elements:
                find_pipeline_elements(elem)

    def extract_from_pipeline_element(pe_node) -> None:
        """
        Extract commands from a pipeline_element node.

        A pipeline_element is either:
        - A simple_command (leaf command)
        - A subshell: (...) with nested compound_command
        - A brace_group: { ...; } with nested compound_command
        """
        if pe_node is None:
            return

        # Check if this is a subshell or brace_group (has nested compound_command)
        if hasattr(pe_node, 'compound_command') and pe_node.compound_command is not None:
            # This is a subshell or brace_group
            if include_wrappers:
                # Add the wrapper text (e.g., "(cmd)" or "{ cmd; }")
                wrapper_text = pe_node.text.strip() if hasattr(pe_node, 'text') else ''
                add_command(wrapper_text)

                # Add the inner compound text (e.g., "cmd1 && cmd2")
                inner = pe_node.compound_command
                inner_text = inner.text.strip() if hasattr(inner, 'text') else ''
                # Strip trailing semicolon for brace groups
                if inner_text.endswith(';'):
                    inner_text = inner_text[:-1].strip()
                add_command(inner_text)

            # Recurse into the compound_command to get leaf commands
            extract_from_compound(pe_node.compound_command)
        else:
            # This is a simple_command - extract its text
            cmd_text = pe_node.text.strip() if hasattr(pe_node, 'text') else ''
            add_command(cmd_text)

            # Check elements for command substitutions within the simple command
            if hasattr(pe_node, 'elements') and pe_node.elements:
                for elem in pe_node.elements:
                    extract_substitutions_from_element(elem)

    def extract_substitutions_from_element(elem) -> None:
        """
        Extract command substitutions from within a simple_command element.

        Command substitutions ($(...) or `...`) contain nested compound_commands.
        """
        if elem is None:
            return

        # Check if this element has a compound_command (it's a substitution)
        if hasattr(elem, 'compound_command') and elem.compound_command is not None:
            # Add the inner compound text (e.g., "cmd1 && cmd2" or "cmd1 | cmd2")
            inner = elem.compound_command
            inner_text = inner.text.strip() if hasattr(inner, 'text') else ''
            # Strip trailing semicolon for brace groups
            if inner_text.endswith(';'):
                inner_text = inner_text[:-1].strip()
            add_command(inner_text)

            # Recurse into the compound_command to extract nested commands
            extract_from_compound(inner)

        # Also check nested elements (substitutions can be deeply nested)
        if hasattr(elem, 'elements') and elem.elements:
            for subelem in elem.elements:
                extract_substitutions_from_element(subelem)

    # Start extraction from the top-level compound_command
    if hasattr(node, 'compound_command') and node.compound_command is not None:
        extract_from_compound(node.compound_command)

    return commands


# Legacy compatibility - maintain old function names
def parse_command_line(command_line: str) -> List[str]:
    """
    Parse a bash command line and extract individual commands.

    This is a legacy compatibility function that wraps extract_commands().
    New code should use extract_commands() directly.

    Args:
        command_line: The bash command line to parse

    Returns:
        List of individual command strings

    Example:
        parse_command_line('git status && rm -rf /')
        ['git status', 'rm -rf /']
        parse_command_line('cat file | grep pattern')
        ['cat file', 'grep pattern']
    """
    return extract_commands(command_line)
