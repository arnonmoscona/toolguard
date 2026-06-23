"""
Unit tests for TOO-17: multi-line Bash command handling (fail-open bypass fix).

These are the LOCKED fixtures (F1-F24) from the TOO-17 design, written TDD-first: most
"bypass" tests are expected to FAIL until the multi-line decomposition fix lands, while the
"regression guard" tests already pass and exist to stop a naive fix from over-splitting
(e.g. shredding heredoc bodies or quoted strings).

All decisions are evaluated through the live path -- ``compound.resolve_compound_permission``
with a ``resolve_one`` closure over ``permissions.check_permission`` -- exactly as the hook
resolves a single level. ``check_permission`` is allow/deny + fail-closed, so any ``'ask'``
outcome here is a NEW behavior the fix must introduce (undecidable segment, or an ASK floor),
never producible by the current code.

Governing principle under test: per-statement validation with strictest-wins (deny > ask >
allow); anything that cannot be safely decomposed resolves to ASK -- never a silent allow of
an undecomposed blob.
"""

import unittest

from toolguard.compound import resolve_compound_permission
from toolguard.parser.multiline import LeafCommand, extract_structured
from toolguard.permissions import check_permission


def _leaf_texts(command: str) -> list[str]:
    """Return the text of every LeafCommand produced by the multi-line extractor.

    Used to pin the rule-authoring surface (e.g. the ``__HEREDOC_TO_<sink>__``
    sentinel and substitution handling) at the structured-extraction contract level.
    """
    return [r.text for r in extract_structured(command) if isinstance(r, LeafCommand)]


def _leaf(command: str, needle: str) -> LeafCommand:
    """Return the single LeafCommand whose text contains *needle* (fails if not exactly one)."""
    matches = [
        r
        for r in extract_structured(command)
        if isinstance(r, LeafCommand) and needle in r.text
    ]
    assert len(matches) == 1, (
        f"expected exactly one leaf containing {needle!r}, got {matches!r}"
    )
    return matches[0]


def _resolve(command: str, allow: list[str], deny: list[str]) -> str:
    """Resolve a (possibly compound/multi-line) command to a bare decision string.

    Mirrors how the hook resolves one hierarchy level: each extracted sub-command is run
    through ``check_permission`` and the compound result is combined strictest-wins.
    """
    decision, _reason = resolve_compound_permission(
        command, lambda c: check_permission(c, allow, deny)
    )
    return decision


class TestMultilineBypassFix(unittest.TestCase):
    """The core fail-open: a dangerous statement on a later line must still be caught.

    (Expected to FAIL until the TOO-17 decomposition fix is implemented.)
    """

    def test_newline_separated_dangerous_second_line_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a multi-line command runs `git status` then `rm -rf /` on the next line
        Then the compound is DENIED (the newline is a statement separator, like `;`)
        """
        self.assertEqual(
            _resolve("git status\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_semicolon_then_newline_dangerous_line_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When the first line ends in `;` and the second line is `rm -rf /`
        Then the compound is DENIED
        """
        self.assertEqual(
            _resolve("git status;\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_trailing_and_operator_continuation_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a line ends with `&&` and the operand `rm -rf /` is on the next line
        Then the two lines form ONE compound and it is DENIED
        """
        self.assertEqual(
            _resolve("git status &&\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_crlf_line_endings_are_handled(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When the statements are separated by a Windows CRLF newline
        Then the dangerous statement is still caught and the compound is DENIED
        """
        self.assertEqual(
            _resolve("git status\r\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_dangerous_command_in_middle_of_linear_sequence_is_denied(self):
        """
        Given allow `cd:*`,`echo:*` and deny `sudo:*`,`rm -rf:*`
        When a three-line sequence has a denied `sudo rm -rf /etc` in the middle
        Then the whole compound is DENIED (not allowed on the first line's match)
        """
        self.assertEqual(
            _resolve(
                "cd x\nsudo rm -rf /etc\necho done",
                ["cd:*", "echo:*"],
                ["sudo:*", "rm -rf:*"],
            ),
            "deny",
        )

    def test_backslash_continuation_joins_into_one_logical_line(self):
        """
        Given allow `cd:*`,`ls:*` (and deny `rm -rf:*`)
        When backslash-continued lines `cd ~/p; \\` + `ls \\` + `-l \\` + `~/` are issued
        Then they join into `cd ~/p` and `ls -l ~/`, both allowed -> ALLOW
        (Currently denies because the mangled continuation matches no allow and fails closed.)
        """
        self.assertEqual(
            _resolve("cd ~/p; \\\nls \\\n-l \\\n~/", ["cd:*", "ls:*"], ["rm -rf:*"]),
            "allow",
        )


class TestMultilineHeredocAndInlineCode(unittest.TestCase):
    """Heredocs and inline interpreter code: bash-family is decomposed; foreign is ASK-floored.

    (Bypass/ask tests expected to FAIL until implemented; body-not-parsed tests are guards.)
    """

    def test_heredoc_into_python_interpreter_asks(self):
        """
        Given allow `uv run*` and deny `rm -rf:*`
        When a heredoc body is fed to the Python interpreter (`uv run python - <<'PY'`)
        Then it resolves to ASK (foreign inline/stdin code; un-downgradable by a broad allow)
        """
        cmd = "uv run python - <<'PY'\nimport os\nos.system('rm -rf /')\nPY"
        self.assertEqual(_resolve(cmd, ["uv run*"], ["rm -rf:*"]), "ask")

    def test_heredoc_into_bash_decomposes_body_and_denies_danger(self):
        """
        Given allow `cat:*`,`bash:*`,`git status:*` and deny `rm -rf:*`
        When a heredoc body containing `rm -rf /` is piped into `bash` (a bash-family sink)
        Then the body is decomposed as bash and the compound is DENIED
        """
        cmd = "cat <<'EOF' | bash\ngit status\nrm -rf /\nEOF"
        self.assertEqual(
            _resolve(cmd, ["cat:*", "bash:*", "git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_heredoc_into_nonexecutor_does_not_parse_body(self):
        """
        Given allow `cat:*`,`pbcopy:*` and deny `rm -rf:*`
        When a heredoc whose body literally contains `rm -rf /` is piped to `pbcopy`
        Then the body is DATA (not parsed); both leaves are allowed -> ALLOW
        (Guard against a naive fix that splits the heredoc body into commands.)
        """
        cmd = "cat <<'EOF' | pbcopy\nrm -rf /\nEOF"
        self.assertEqual(_resolve(cmd, ["cat:*", "pbcopy:*"], ["rm -rf:*"]), "allow")

    def test_bash_dash_c_inner_string_is_decomposed_and_denied(self):
        """
        Given allow `bash -c:*`,`git status:*` and deny `rm -rf:*`
        When `bash -c "git status; rm -rf /"` is issued
        Then the inner string is decomposed as bash and the compound is DENIED
        (Currently allowed because `bash -c:*` matches the whole opaque string.)
        """
        cmd = 'bash -c "git status; rm -rf /"'
        self.assertEqual(
            _resolve(cmd, ["bash -c:*", "git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_uv_python_dash_c_inline_code_asks(self):
        """
        Given allow `uv run*` and deny `rm -rf:*`
        When `uv run python -c "<multiline python>"` is issued
        Then it resolves to ASK (inline foreign code floor; `uv run*` cannot downgrade it)
        """
        cmd = "uv run python -c \"\nimport os\nos.system('rm -rf /')\n\""
        self.assertEqual(_resolve(cmd, ["uv run*"], ["rm -rf:*"]), "ask")

    def test_python_dash_c_inline_code_asks(self):
        """
        Given allow `python3 -c:*` and deny `rm -rf:*`
        When `python3 -c "..."` carries inline Python (even one mentioning rm -rf)
        Then it resolves to ASK (inline foreign code floor; not parsed as bash, not allowed)
        """
        cmd = "python3 -c \"import os; os.system('rm -rf /')\""
        self.assertEqual(_resolve(cmd, ["python3 -c:*"], ["rm -rf:*"]), "ask")


class TestMultilineControlStructuresAndProcsub(unittest.TestCase):
    """Simple constructs decompose; complex/un-decomposable constructs resolve to ASK.

    (Expected to FAIL until implemented.)
    """

    def test_simple_for_loop_body_is_validated(self):
        """
        Given allow `echo:*`,`grep:*` (and deny `rm -rf:*`)
        When a non-nested `for` loop runs only `echo` and `grep` in its body
        Then the body commands are validated and the compound is ALLOWED
        """
        cmd = "for f in a b; do echo $f; grep $f g; done"
        self.assertEqual(_resolve(cmd, ["echo:*", "grep:*"], ["rm -rf:*"]), "allow")

    def test_simple_for_loop_with_dangerous_body_is_denied(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When a non-nested `for` loop body contains `rm -rf $f`
        Then the body is validated and the compound is DENIED
        """
        cmd = "for f in a b; do echo $f; rm -rf $f; done"
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "deny")

    def test_simple_for_loop_with_newline_body_is_validated(self):
        """
        Given allow `echo:*` (and deny `rm -rf:*`)
        When a non-nested `for` loop uses a newline-separated body (the common real form,
            not the `;`-delimited form)
        Then the body is decomposed and the safe compound is ALLOWED (same as the `;` form)
        """
        cmd = "for f in a b; do\n  echo $f\ndone"
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "allow")

    def test_simple_for_loop_with_newline_body_and_danger_is_denied(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When a non-nested `for` loop with a newline-separated body contains `rm -rf $f`
        Then the body is decomposed, the danger is caught, and the compound is DENIED
            (must match the `;`-delimited form's behavior -- not silently downgrade to ASK)
        """
        cmd = "for f in a b; do\n  echo $f\n  rm -rf $f\ndone"
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "deny")

    def test_complex_nested_control_structure_asks(self):
        """
        Given any allow/deny config
        When a command nests a `while` loop around an `if`/`else`
        Then it is too complex to decompose and resolves to ASK
        """
        cmd = 'while read l; do if [ -e "$l" ]; then echo ok; else echo no; fi; done'
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "ask")

    def test_process_substitution_asks(self):
        """
        Given allow `diff:*` (and deny `rm -rf:*`)
        When a command uses process substitution `diff <(sort a) <(sort b)`
        Then the inner commands cannot be safely decomposed today and it resolves to ASK
        (Currently allowed as one opaque `diff ...` command -- a latent fail-open.)
        """
        cmd = "diff <(sort a) <(sort b)"
        self.assertEqual(_resolve(cmd, ["diff:*"], ["rm -rf:*"]), "ask")


class TestMultilineRegressionGuards(unittest.TestCase):
    """Already-passing guards: ensure the fix does not over-split quotes/comments/banners."""

    def test_linear_allowed_sequence_is_allowed(self):
        """
        Given allow `cd:*`,`echo:*`,`grep:*` (and deny `rm -rf:*`)
        When a benign multi-line banner sequence runs cd/echo/grep across lines
        Then every statement is allowed and the compound is ALLOWED
        """
        cmd = 'cd x\necho "=== a ===" && grep -rn p f\necho ""'
        self.assertEqual(
            _resolve(cmd, ["cd:*", "echo:*", "grep:*"], ["rm -rf:*"]), "allow"
        )

    def test_quoted_separators_are_not_split(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo "rm -rf /; safe"` carries `rm -rf` inside a quoted argument
        Then the quoted content is not a command and the compound is ALLOWED
        """
        self.assertEqual(
            _resolve('echo "rm -rf /; safe"', ["echo:*"], ["rm -rf:*"]), "allow"
        )

    def test_hash_inside_argument_is_not_a_comment(self):
        """
        Given allow `echo:*`
        When `echo http://x#frag` contains a `#` mid-argument (not at a word boundary)
        Then it is not treated as a comment and the command is ALLOWED
        """
        self.assertEqual(_resolve("echo http://x#frag", ["echo:*"], []), "allow")

    def test_full_line_comment_is_dropped(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a leading full-line comment `# rm -rf /` precedes `git status`
        Then the comment is dropped and the compound is ALLOWED
        (Currently denied because the comment+command blob matches no allow.)
        """
        self.assertEqual(
            _resolve("# rm -rf /\ngit status", ["git status:*"], ["rm -rf:*"]), "allow"
        )

    def test_blank_lines_and_padding_are_trimmed(self):
        """
        Given allow `git status:*`
        When the command has leading/trailing blank lines and surrounding whitespace
        Then padding is trimmed and the single statement is ALLOWED
        """
        self.assertEqual(_resolve("\n\n  git status \n", ["git status:*"], []), "allow")


class TestHeredocSentinelShape(unittest.TestCase):
    """Pin the ``__HEREDOC_TO_<sink>__`` rule-authoring surface (was untested).

    These assert the structured-extraction CONTRACT (leaf text + ask_floor), which is the
    surface rule authors write against -- so it must survive the planned IR refactor.
    """

    def test_nonexec_sink_emits_sentinel_without_ask_floor(self):
        """
        Given a heredoc piped to a non-executor (`cat <<EOF | pbcopy`)
        When the command is structured-extracted
        Then the bearer leaf is `cat __HEREDOC_TO_pbcopy__` with ask_floor False, the `pbcopy`
            leaf is present, and the heredoc body is NOT a command leaf
        """
        cmd = "cat <<'EOF' | pbcopy\nrm -rf /\nEOF"
        texts = _leaf_texts(cmd)
        self.assertIn("cat __HEREDOC_TO_pbcopy__", texts)
        self.assertIn("pbcopy", texts)
        self.assertNotIn("rm -rf /", texts)
        self.assertFalse(_leaf(cmd, "__HEREDOC_TO_pbcopy__").ask_floor)

    def test_sentinel_preserves_bearer_arguments(self):
        """
        Given a heredoc on a command with dangerous args (`tee /etc/passwd <<EOF`)
        When structured-extracted
        Then the bearer args are preserved in the leaf (`tee /etc/passwd __HEREDOC_TO_tee__`)
            so a deny on the bearer/args can still fire
        """
        self.assertIn(
            "tee /etc/passwd __HEREDOC_TO_tee__",
            _leaf_texts("tee /etc/passwd <<'EOF'\nx\nEOF"),
        )

    def test_foreign_sink_sentinel_has_ask_floor(self):
        """
        Given a heredoc fed to the Python interpreter via `uv run python -`
        When structured-extracted
        Then the sink resolves to `python` and the sentinel leaf carries ask_floor True
        """
        leaf = _leaf("uv run python - <<'PY'\nx\nPY", "__HEREDOC_TO_python__")
        self.assertTrue(leaf.ask_floor)

    def test_bash_family_sink_decomposes_body_with_no_sentinel(self):
        """
        Given a heredoc piped to `bash` (a bash-family sink)
        When structured-extracted
        Then the body is decomposed into command leaves and NO `__HEREDOC_TO_` sentinel is emitted
        """
        texts = _leaf_texts("cat <<'EOF' | bash\ngit status\nrm -rf /\nEOF")
        self.assertIn("rm -rf /", texts)
        self.assertIn("git status", texts)
        self.assertFalse(any("__HEREDOC_TO_" in t for t in texts))

    def test_sentinel_is_matchable_by_a_rule_deny(self):
        """
        Given a deny rule targeting the heredoc sentinel (`[regex]__HEREDOC_TO_`)
        When a non-executor heredoc (`cat <<EOF | pbcopy`) is resolved
        Then the sentinel leaf matches the deny and the compound is DENIED
        """
        self.assertEqual(
            _resolve(
                "cat <<'EOF' | pbcopy\nx\nEOF", ["pbcopy:*"], ["[regex]__HEREDOC_TO_"]
            ),
            "deny",
        )

    def test_sentinel_is_matchable_by_a_rule_allow(self):
        """
        Given an allow rule targeting a specific non-exec sink (`[regex]__HEREDOC_TO_pbcopy__`)
        When a `cat <<EOF | pbcopy` heredoc is resolved (with pbcopy allowed)
        Then both leaves are allowed and the compound is ALLOWED
        """
        self.assertEqual(
            _resolve(
                "cat <<'EOF' | pbcopy\nx\nEOF",
                ["[regex]__HEREDOC_TO_pbcopy__", "pbcopy:*"],
                [],
            ),
            "allow",
        )


class TestCommandSubstitution(unittest.TestCase):
    """Inner commands of `` `...` `` / `$(...)` substitutions are extracted and gated."""

    def test_backtick_inner_command_is_gated(self):
        """
        Given allow `rm:*` and deny `ls:*`
        When the outer `rm` takes a backtick substitution running the denied `ls`
        Then the inner `ls` is validated and the compound is DENIED
        """
        self.assertEqual(_resolve("rm `ls`", ["rm:*"], ["ls:*"]), "deny")

    def test_dollar_paren_inner_command_is_gated(self):
        """
        Given allow `rm:*` and deny `ls:*`
        When the outer `rm` takes a `$(...)` substitution running the denied `ls`
        Then the inner `ls` is validated and the compound is DENIED
        """
        self.assertEqual(_resolve("rm $(ls)", ["rm:*"], ["ls:*"]), "deny")

    def test_nested_substitution_inner_command_is_gated(self):
        """
        Given allow `echo:*`,`ls:*` and deny `pwd:*`
        When a nested substitution `echo $(ls $(pwd))` runs the denied `pwd`
        Then the deepest inner command is validated and the compound is DENIED
        """
        self.assertEqual(
            _resolve("echo $(ls $(pwd))", ["echo:*", "ls:*"], ["pwd:*"]), "deny"
        )

    def test_substitution_all_inner_allowed_is_allowed(self):
        """
        Given allow `rm:*`,`ls:*`
        When `rm `ls`` has both outer and inner commands allowed
        Then the compound is ALLOWED
        """
        self.assertEqual(_resolve("rm `ls`", ["rm:*", "ls:*"], []), "allow")


class TestControlStructureClassification(unittest.TestCase):
    """Simple constructs decompose; else/elif, case, and nesting resolve to ASK."""

    def test_simple_if_dangerous_body_is_denied(self):
        """
        Given allow `grep:*` and deny `rm -rf:*`
        When a non-nested `if ...; then ...; fi` (no else) has `rm -rf x` in its body
        Then the body is decomposed and the compound is DENIED
        """
        self.assertEqual(
            _resolve("if grep -q foo f; then rm -rf x; fi", ["grep:*"], ["rm -rf:*"]),
            "deny",
        )

    def test_simple_if_safe_body_is_allowed(self):
        """
        Given allow `grep:*`,`cat:*` and deny `rm -rf:*`
        When a simple `if grep ...; then cat f; fi` has only allowed commands
        Then the condition and body are validated and the compound is ALLOWED
        """
        self.assertEqual(
            _resolve(
                "if grep -q foo f; then cat f; fi", ["grep:*", "cat:*"], ["rm -rf:*"]
            ),
            "allow",
        )

    def test_posix_test_condition_is_not_treated_as_a_command(self):
        """
        Given allow `cat:*` only (no rule for the `[` test builtin)
        When `if [ -f x ]; then cat f; fi` is resolved
        Then the `[ -f x ]` test is not a command needing a rule and the compound is ALLOWED
        """
        self.assertEqual(
            _resolve("if [ -f x ]; then cat f; fi", ["cat:*"], ["rm -rf:*"]), "allow"
        )

    def test_if_with_else_asks(self):
        """
        Given allow `echo:*`
        When an `if ...; then ...; else ...; fi` has an else branch
        Then it is too complex to decompose and resolves to ASK
        """
        self.assertEqual(
            _resolve("if [ -f x ]; then echo a; else echo b; fi", ["echo:*"], []), "ask"
        )

    def test_case_statement_asks(self):
        """
        Given allow `echo:*`
        When a `case ... esac` statement is resolved
        Then it is not statically decomposed and resolves to ASK
        """
        self.assertEqual(
            _resolve("case $x in a) echo hi;; esac", ["echo:*"], []), "ask"
        )

    def test_foreign_node_inline_code_asks(self):
        """
        Given allow `node -e:*`
        When `node -e "..."` carries inline JavaScript
        Then it resolves to ASK (inline foreign code floor; allow cannot downgrade it)
        """
        self.assertEqual(
            _resolve('node -e "process.exit(0)"', ["node -e:*"], []), "ask"
        )


class TestQuoteRobustness(unittest.TestCase):
    """Escaped/closed quotes must not let a hidden statement leak out of a quoted argument."""

    def test_escaped_double_quote_does_not_split_statement(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo "a\\"b; rm -rf /"` has an escaped quote before a `; rm -rf /` inside the string
        Then the escaped quote does not close the string, the `rm -rf` stays quoted data, and
            the compound is ALLOWED
        """
        self.assertEqual(
            _resolve(r'echo "a\"b; rm -rf /"', ["echo:*"], ["rm -rf:*"]), "allow"
        )

    def test_single_quote_idiom_does_not_split_statement(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo 'a'\\''b; rm -rf /'` uses the `'\\''` single-quote idiom around a `; rm -rf /`
        Then the content stays a single quoted argument and the compound is ALLOWED
        """
        self.assertEqual(
            _resolve(r"echo 'a'\''b; rm -rf /'", ["echo:*"], ["rm -rf:*"]), "allow"
        )


class TestForeignInterpreterVersionRobustness(unittest.TestCase):
    """Versioned interpreters are recognized dynamically (no hard-coded version list)."""

    def test_future_python_minor_version_inline_code_is_floored(self):
        """
        Given allow `python3.14 -c:*` (a Python version not enumerated anywhere)
        When `python3.14 -c "..."` runs inline code
        Then it is still recognized as a foreign interpreter and ASK-floored (allow can't downgrade)
        """
        self.assertEqual(
            _resolve('python3.14 -c "import os"', ["python3.14 -c:*"], []), "ask"
        )

    def test_arbitrary_python_minor_version_inline_code_is_floored(self):
        """
        Given allow `python3.99 -c:*`
        When an arbitrary far-future Python minor version runs inline code
        Then it is ASK-floored (prefix recognition, not a maintained version list)
        """
        self.assertEqual(_resolve('python3.99 -c "x"', ["python3.99 -c:*"], []), "ask")

    def test_heredoc_into_versioned_python_asks(self):
        """
        Given allow `python3.13:*`
        When a heredoc is fed to `python3.13` (a versioned interpreter)
        Then the sink is recognized as foreign and the compound resolves to ASK
        """
        self.assertEqual(
            _resolve("python3.13 - <<'PY'\nx\nPY", ["python3.13:*"], []), "ask"
        )


if __name__ == "__main__":
    unittest.main()
