"""Unit tests for TOO-17: multi-line Bash command handling (fail-open bypass fix)."""

import unittest

from toolguard.compound import decompose, resolve_compound_permission
from toolguard.parser.command_extractor import LeafCommand
from toolguard.parser.multiline import extract_structured
from toolguard.permissions import check_permission


def _extracted(command: str) -> list[tuple]:
    """Every extraction result in order: ``('leaf', text, ask_floor)`` / ``('undecidable', reason)``.

    Asserted exactly, because a decision alone cannot tell correct decomposition
    from a total extraction loss: an empty extraction fails CLOSED to ``deny``
    and any undecidable segment floors to ``ask``.
    """
    rows: list[tuple] = []
    for result in extract_structured(command):
        if isinstance(result, LeafCommand):
            rows.append(("leaf", result.text, result.ask_floor))
        else:
            rows.append(("undecidable", result.reason))
    return rows


def _parts(command: str) -> list[tuple]:
    """The sub-command tuple of each decomposed unit -- the strings a rule actually sees."""
    return [unit.parts for unit in decompose(command)]


def _resolve(command: str, allow: list[str], deny: list[str]) -> str:
    """Resolve a (possibly compound/multi-line) command to a bare decision string."""
    return resolve_compound_permission(
        command, lambda c: (*check_permission(c, allow, deny), None)
    ).decision


class TestMultilineBypassFix(unittest.TestCase):
    """The core fail-open: a dangerous statement on a later line must still be caught."""

    def test_newline_separated_dangerous_second_line_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a multi-line command runs `git status` then `rm -rf /` on the next line
        Then both lines become separate leaves (the newline is a statement separator,
            like `;`) and the compound is DENIED
        """
        self.assertEqual(
            _extracted("git status\nrm -rf /"),
            [("leaf", "git status", False), ("leaf", "rm -rf /", False)],
        )
        self.assertEqual(
            _resolve("git status\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_semicolon_then_newline_dangerous_line_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When the first line ends in `;` and the second line is `rm -rf /`
        Then both lines become separate leaves and the compound is DENIED
        """
        self.assertEqual(
            _extracted("git status;\nrm -rf /"),
            [("leaf", "git status", False), ("leaf", "rm -rf /", False)],
        )
        self.assertEqual(
            _resolve("git status;\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_trailing_and_operator_continuation_is_denied(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a line ends with `&&` and the operand `rm -rf /` is on the next line
        Then the two lines form ONE compound of two leaves and it is DENIED
        """
        self.assertEqual(
            _extracted("git status &&\nrm -rf /"),
            [("leaf", "git status", False), ("leaf", "rm -rf /", False)],
        )
        self.assertEqual(
            _resolve("git status &&\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_crlf_line_endings_are_handled(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When the statements are separated by a Windows CRLF newline
        Then both statements still become separate leaves and the compound is DENIED

        DOES NOT PIN `_normalize_line_endings`: measured 2026-08-12, the grammar's
        `line_ws_char <- [ \\t\\n\\r]` splits CRLF and lone CR on its own, so removing
        the pre-pass normaliser changes nothing here or anywhere in this module.
        """
        self.assertEqual(
            _extracted("git status\r\nrm -rf /"),
            [("leaf", "git status", False), ("leaf", "rm -rf /", False)],
        )
        self.assertEqual(
            _resolve("git status\r\nrm -rf /", ["git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_dangerous_command_in_middle_of_linear_sequence_is_denied(self):
        """
        Given allow `cd:*`,`echo:*` and deny `sudo:*`,`rm -rf:*`
        When a three-line sequence has a denied `sudo rm -rf /etc` in the middle
        Then all three lines become leaves and the whole compound is DENIED (not
            allowed on the first line's match)
        """
        cmd = "cd x\nsudo rm -rf /etc\necho done"
        self.assertEqual(
            _extracted(cmd),
            [
                ("leaf", "cd x", False),
                ("leaf", "sudo rm -rf /etc", False),
                ("leaf", "echo done", False),
            ],
        )
        self.assertEqual(
            _resolve(cmd, ["cd:*", "echo:*"], ["sudo:*", "rm -rf:*"]), "deny"
        )

    def test_backslash_continuation_joins_into_one_logical_line(self):
        """
        Given allow `cd:*`,`ls:*` (and deny `rm -rf:*`)
        When backslash-continued lines `cd ~/p; \\` + `ls \\` + `-l \\` + `~/` are issued
        Then they join into exactly two leaves, `cd ~/p` and `ls -l ~/` -> ALLOW
        """
        cmd = "cd ~/p; \\\nls \\\n-l \\\n~/"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "cd ~/p", False), ("leaf", "ls -l ~/", False)],
        )
        self.assertEqual(_resolve(cmd, ["cd:*", "ls:*"], ["rm -rf:*"]), "allow")


class TestMultilineHeredocAndInlineCode(unittest.TestCase):
    """Heredocs and inline interpreter code: bash-family is decomposed; foreign is ASK-floored."""

    def test_heredoc_into_python_interpreter_asks(self):
        """
        Given allow `uv run*` and deny `rm -rf:*`
        When a heredoc body is fed to the Python interpreter (`uv run python - <<'PY'`)
        Then the body is discarded behind one ask_floor sentinel leaf and the command
            resolves to ASK (un-downgradable by a broad allow)
        """
        cmd = "uv run python - <<'PY'\nimport os\nos.system('rm -rf /')\nPY"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "uv run python - __HEREDOC_TO_python__", True)],
        )
        self.assertEqual(_resolve(cmd, ["uv run*"], ["rm -rf:*"]), "ask")

    def test_heredoc_into_bash_decomposes_body_and_denies_danger(self):
        """
        Given allow `cat:*`,`bash:*`,`git status:*` and deny `rm -rf:*`
        When a heredoc body containing `rm -rf /` is piped into `bash` (a bash-family sink)
        Then the body lines become leaves of their own and the compound is DENIED
        """
        cmd = "cat <<'EOF' | bash\ngit status\nrm -rf /\nEOF"
        self.assertEqual(
            _extracted(cmd),
            [
                ("leaf", "git status", False),
                ("leaf", "rm -rf /", False),
                ("leaf", "cat", False),
                ("leaf", "bash", False),
            ],
        )
        self.assertEqual(
            _resolve(cmd, ["cat:*", "bash:*", "git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_heredoc_into_nonexecutor_does_not_parse_body(self):
        """
        Given allow `cat:*`,`pbcopy:*` and deny `rm -rf:*`
        When a heredoc whose body literally contains `rm -rf /` is piped to `pbcopy`
        Then the body is DATA -- it is not a leaf -- and both real leaves are allowed
        """
        cmd = "cat <<'EOF' | pbcopy\nrm -rf /\nEOF"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "cat __HEREDOC_TO_pbcopy__", False), ("leaf", "pbcopy", False)],
        )
        self.assertEqual(_resolve(cmd, ["cat:*", "pbcopy:*"], ["rm -rf:*"]), "allow")

    def test_bash_dash_c_inner_string_is_decomposed_and_denied(self):
        """
        Given allow `bash -c:*`,`git status:*` and deny `rm -rf:*`
        When `bash -c "git status; rm -rf /"` is issued
        Then the inner string is decomposed into its own leaves (the `bash -c` wrapper
            is not a leaf) and the compound is DENIED
        """
        cmd = 'bash -c "git status; rm -rf /"'
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "git status", False), ("leaf", "rm -rf /", False)],
        )
        self.assertEqual(
            _resolve(cmd, ["bash -c:*", "git status:*"], ["rm -rf:*"]), "deny"
        )

    def test_uv_python_dash_c_inline_code_asks(self):
        """
        Given allow `uv run*` and deny `rm -rf:*`
        When `uv run python -c "<multiline python>"` is issued
        Then the whole invocation is one ask_floor leaf -- the Python is never split
            into bash leaves -- and it resolves to ASK
        """
        cmd = "uv run python -c \"\nimport os\nos.system('rm -rf /')\n\""
        self.assertEqual(
            _extracted(cmd),
            [
                (
                    "leaf",
                    "uv run python -c \"\nimport os\nos.system('rm -rf /')\n\"",
                    True,
                )
            ],
        )
        self.assertEqual(_resolve(cmd, ["uv run*"], ["rm -rf:*"]), "ask")

    def test_python_dash_c_inline_code_asks(self):
        """
        Given allow `python3 -c:*` and deny `rm -rf:*`
        When `python3 -c "..."` carries inline Python (even one mentioning rm -rf)
        Then it is one ask_floor leaf and resolves to ASK (not parsed as bash, and the
            allow cannot downgrade it)
        """
        cmd = "python3 -c \"import os; os.system('rm -rf /')\""
        self.assertEqual(_extracted(cmd), [("leaf", cmd, True)])
        self.assertEqual(_resolve(cmd, ["python3 -c:*"], ["rm -rf:*"]), "ask")


class TestMultilineControlStructuresAndProcsub(unittest.TestCase):
    """Simple constructs decompose; complex/un-decomposable constructs resolve to ASK."""

    def test_simple_for_loop_body_is_validated(self):
        """
        Given allow `echo:*`,`grep:*` (and deny `rm -rf:*`)
        When a non-nested `for` loop runs only `echo` and `grep` in its body
        Then each body command is its own leaf and the compound is ALLOWED
        """
        cmd = "for f in a b; do echo $f; grep $f g; done"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "echo $f", False), ("leaf", "grep $f g", False)],
        )
        self.assertEqual(_resolve(cmd, ["echo:*", "grep:*"], ["rm -rf:*"]), "allow")

    def test_simple_for_loop_with_dangerous_body_is_denied(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When a non-nested `for` loop body contains `rm -rf $f`
        Then `rm -rf $f` is a leaf in its own right and the compound is DENIED
        """
        cmd = "for f in a b; do echo $f; rm -rf $f; done"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "echo $f", False), ("leaf", "rm -rf $f", False)],
        )
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "deny")

    def test_simple_for_loop_with_newline_body_is_validated(self):
        """
        Given allow `echo:*` (and deny `rm -rf:*`)
        When a non-nested `for` loop uses a newline-separated body (the common real form,
            not the `;`-delimited form)
        Then the body is decomposed into leaves and the safe compound is ALLOWED
        """
        cmd = "for f in a b; do\n  echo $f\ndone"
        self.assertEqual(_extracted(cmd), [("leaf", "echo $f", False)])
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "allow")

    def test_simple_for_loop_with_newline_body_and_danger_is_denied(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When a non-nested `for` loop with a newline-separated body contains `rm -rf $f`
        Then it yields the same two leaves as the `;`-delimited form and is DENIED
            (not silently downgraded to ASK)
        """
        cmd = "for f in a b; do\n  echo $f\n  rm -rf $f\ndone"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "echo $f", False), ("leaf", "rm -rf $f", False)],
        )
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "deny")

    def test_complex_nested_control_structure_asks(self):
        """
        Given any allow/deny config
        When a command nests a `while` loop around an `if`/`else`
        Then the nested-control guard makes the whole loop ONE undecidable segment,
            naming that guard, and it resolves to ASK
        """
        cmd = 'while read l; do if [ -e "$l" ]; then echo ok; else echo no; fi; done'
        self.assertEqual(
            _extracted(cmd),
            [
                (
                    "undecidable",
                    "loop with nested control structure cannot be statically decomposed",
                )
            ],
        )
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "ask")

    def test_process_substitution_asks(self):
        """
        Given allow `diff:*` (and deny `rm -rf:*`)
        When a command uses process substitution `diff <(sort a) <(sort b)`
        Then it becomes one undecidable segment naming process substitution -- the inner
            `sort` commands are never leaves -- and it resolves to ASK
        """
        cmd = "diff <(sort a) <(sort b)"
        self.assertEqual(
            _extracted(cmd),
            [
                (
                    "undecidable",
                    "command contains process substitution <(...) or >(...)",
                )
            ],
        )
        self.assertEqual(_resolve(cmd, ["diff:*"], ["rm -rf:*"]), "ask")


class TestMultilineRegressionGuards(unittest.TestCase):
    """Guards: the fix must not over-split quotes/comments/banners."""

    def test_linear_allowed_sequence_is_allowed(self):
        """
        Given allow `cd:*`,`echo:*`,`grep:*` (and deny `rm -rf:*`)
        When a benign multi-line banner sequence runs cd/echo/grep across lines
        Then it splits into exactly four leaves, all allowed -> ALLOW
        """
        cmd = 'cd x\necho "=== a ===" && grep -rn p f\necho ""'
        self.assertEqual(
            _extracted(cmd),
            [
                ("leaf", "cd x", False),
                ("leaf", 'echo "=== a ==="', False),
                ("leaf", "grep -rn p f", False),
                ("leaf", 'echo ""', False),
            ],
        )
        self.assertEqual(
            _resolve(cmd, ["cd:*", "echo:*", "grep:*"], ["rm -rf:*"]), "allow"
        )

    def test_quoted_separators_are_not_split(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo "rm -rf /; safe"` carries `rm -rf` inside a quoted argument
        Then the whole thing stays ONE leaf (the quoted `;` is not a separator) -> ALLOW
        """
        cmd = 'echo "rm -rf /; safe"'
        self.assertEqual(_extracted(cmd), [("leaf", cmd, False)])
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "allow")

    def test_hash_inside_argument_is_not_a_comment(self):
        """
        Given allow `echo:*`
        When `echo http://x#frag` contains a `#` mid-argument (not at a word boundary)
        Then the fragment SURVIVES INTO THE LEAF -- it is not treated as a comment --
            and the command is ALLOWED

        The leaf assertion is the load-bearing one. The decision alone cannot fail:
        stripping `#frag` leaves `echo http://x`, which matches `echo:*` just as well
        (follow-up-queue MB3, shape 4).
        """
        self.assertEqual(
            _extracted("echo http://x#frag"), [("leaf", "echo http://x#frag", False)]
        )
        self.assertEqual(_resolve("echo http://x#frag", ["echo:*"], []), "allow")

    def test_full_line_comment_is_dropped(self):
        """
        Given allow `git status:*` and deny `rm -rf:*`
        When a leading full-line comment `# rm -rf /` precedes `git status`
        Then the comment yields no leaf at all and the compound is ALLOWED

        Two mechanisms strip comments -- `multiline._strip_comments` and the grammar's
        own `comment` rule -- and each alone is invisible here (shape 19). Disabling
        only one leaves this test green; that is measured, not assumed.
        """
        cmd = "# rm -rf /\ngit status"
        self.assertEqual(_extracted(cmd), [("leaf", "git status", False)])
        self.assertEqual(_resolve(cmd, ["git status:*"], ["rm -rf:*"]), "allow")

    def test_blank_lines_and_padding_are_trimmed(self):
        """
        Given allow `git status:*`
        When the command has leading/trailing blank lines and surrounding whitespace
        Then a single trimmed leaf comes out and it is ALLOWED

        Same masking as the comment case: `_collapse_whitespace` and the grammar's
        `line_ws` both do this, so neither is detectable alone.
        """
        self.assertEqual(
            _extracted("\n\n  git status \n"), [("leaf", "git status", False)]
        )
        self.assertEqual(_resolve("\n\n  git status \n", ["git status:*"], []), "allow")


class TestHeredocSentinelShape(unittest.TestCase):
    """Pin the ``__HEREDOC_TO_<sink>__`` rule-authoring surface: leaf text and ask_floor."""

    def test_nonexec_sink_emits_sentinel_without_ask_floor(self):
        """
        Given a heredoc piped to a non-executor (`cat <<EOF | pbcopy`)
        When the command is structured-extracted
        Then the result is exactly the bearer leaf `cat __HEREDOC_TO_pbcopy__` with
            ask_floor False plus the `pbcopy` leaf -- the body is not a command leaf
        """
        self.assertEqual(
            _extracted("cat <<'EOF' | pbcopy\nrm -rf /\nEOF"),
            [("leaf", "cat __HEREDOC_TO_pbcopy__", False), ("leaf", "pbcopy", False)],
        )

    def test_sentinel_preserves_bearer_arguments(self):
        """
        Given a heredoc on a command with dangerous args (`tee /etc/passwd <<EOF`)
        When structured-extracted
        Then the bearer args are preserved in the one leaf
            (`tee /etc/passwd __HEREDOC_TO_tee__`) so a deny on the bearer/args can fire
        """
        self.assertEqual(
            _extracted("tee /etc/passwd <<'EOF'\nx\nEOF"),
            [("leaf", "tee /etc/passwd __HEREDOC_TO_tee__", False)],
        )

    def test_foreign_sink_sentinel_has_ask_floor(self):
        """
        Given a heredoc fed to the Python interpreter via `uv run python -`
        When structured-extracted
        Then the sink resolves to `python` and that single leaf carries ask_floor True
        """
        self.assertEqual(
            _extracted("uv run python - <<'PY'\nx\nPY"),
            [("leaf", "uv run python - __HEREDOC_TO_python__", True)],
        )

    def test_bash_family_sink_decomposes_body_with_no_sentinel(self):
        """
        Given a heredoc piped to `bash` (a bash-family sink)
        When structured-extracted
        Then the body is decomposed into command leaves and NO `__HEREDOC_TO_` sentinel
            is emitted
        """
        self.assertEqual(
            _extracted("cat <<'EOF' | bash\ngit status\nrm -rf /\nEOF"),
            [
                ("leaf", "git status", False),
                ("leaf", "rm -rf /", False),
                ("leaf", "cat", False),
                ("leaf", "bash", False),
            ],
        )

    def test_sentinel_is_matchable_by_a_rule_deny(self):
        """
        Given a deny rule targeting the heredoc sentinel (`[regex]__HEREDOC_TO_`)
        When a non-executor heredoc (`cat <<EOF | pbcopy`) is resolved
        Then the sentinel leaf matches the deny and the compound is DENIED
        """
        cmd = "cat <<'EOF' | pbcopy\nx\nEOF"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "cat __HEREDOC_TO_pbcopy__", False), ("leaf", "pbcopy", False)],
        )
        self.assertEqual(_resolve(cmd, ["pbcopy:*"], ["[regex]__HEREDOC_TO_"]), "deny")

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
    """Inner commands of `` `...` `` / `$(...)` substitutions become their own sub-commands."""

    def test_backtick_inner_command_is_gated(self):
        """
        Given allow `rm:*` and deny `ls:*`
        When the outer `rm` takes a backtick substitution running the denied `ls`
        Then `ls` is a sub-command of the single leaf and the compound is DENIED
        """
        self.assertEqual(_parts("rm `ls`"), [("rm `ls`", "ls")])
        self.assertEqual(_resolve("rm `ls`", ["rm:*"], ["ls:*"]), "deny")

    def test_dollar_paren_inner_command_is_gated(self):
        """
        Given allow `rm:*` and deny `ls:*`
        When the outer `rm` takes a `$(...)` substitution running the denied `ls`
        Then `ls` is a sub-command of the single leaf and the compound is DENIED
        """
        self.assertEqual(_parts("rm $(ls)"), [("rm $(ls)", "ls")])
        self.assertEqual(_resolve("rm $(ls)", ["rm:*"], ["ls:*"]), "deny")

    def test_nested_substitution_inner_command_is_gated(self):
        """
        Given allow `echo:*`,`ls:*` and deny `pwd:*`
        When a nested substitution `echo $(ls $(pwd))` runs the denied `pwd`
        Then every nesting level -- including the innermost `pwd` -- is a sub-command
            and the compound is DENIED
        """
        self.assertEqual(
            _parts("echo $(ls $(pwd))"),
            [("echo $(ls $(pwd))", "ls $(pwd)", "pwd")],
        )
        self.assertEqual(
            _resolve("echo $(ls $(pwd))", ["echo:*", "ls:*"], ["pwd:*"]), "deny"
        )

    def test_substitution_all_inner_allowed_is_allowed(self):
        """
        Given allow `rm:*`,`ls:*`
        When ``rm `ls` `` has both outer and inner commands allowed
        Then the inner `ls` IS presented as its own sub-command and the compound is ALLOWED

        The parts assertion is the load-bearing one: the decision alone cannot fail,
        since never descending into the substitution also yields ALLOW on `rm:*`
        (shape 20 -- ticket 34's defect wears exactly this shape).
        """
        self.assertEqual(_parts("rm `ls`"), [("rm `ls`", "ls")])
        self.assertEqual(_resolve("rm `ls`", ["rm:*", "ls:*"], []), "allow")


class TestControlStructureClassification(unittest.TestCase):
    """Simple constructs decompose; else/elif, case, and nesting resolve to ASK."""

    def test_simple_if_dangerous_body_is_denied(self):
        """
        Given allow `grep:*` and deny `rm -rf:*`
        When a non-nested `if ...; then ...; fi` (no else) has `rm -rf x` in its body
        Then the condition AND the body each become leaves and the compound is DENIED
        """
        cmd = "if grep -q foo f; then rm -rf x; fi"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "grep -q foo f", False), ("leaf", "rm -rf x", False)],
        )
        self.assertEqual(_resolve(cmd, ["grep:*"], ["rm -rf:*"]), "deny")

    def test_simple_if_safe_body_is_allowed(self):
        """
        Given allow `grep:*`,`cat:*` and deny `rm -rf:*`
        When a simple `if grep ...; then cat f; fi` has only allowed commands
        Then the condition command is emitted as a leaf alongside the body's, and the
            compound is ALLOWED
        """
        cmd = "if grep -q foo f; then cat f; fi"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "grep -q foo f", False), ("leaf", "cat f", False)],
        )
        self.assertEqual(_resolve(cmd, ["grep:*", "cat:*"], ["rm -rf:*"]), "allow")

    def test_posix_test_condition_is_not_treated_as_a_command(self):
        """
        Given allow `cat:*` only (no rule for the `[` test builtin)
        When `if [ -f x ]; then cat f; fi` is resolved
        Then `[ -f x ]` produces NO leaf -- it is a test, not a command -- and the
            compound is ALLOWED on `cat f` alone
        """
        cmd = "if [ -f x ]; then cat f; fi"
        self.assertEqual(_extracted(cmd), [("leaf", "cat f", False)])
        self.assertEqual(_resolve(cmd, ["cat:*"], ["rm -rf:*"]), "allow")

    def test_if_with_else_asks(self):
        """
        Given allow `echo:*`
        When an `if ...; then ...; else ...; fi` has an else branch
        Then the else/elif guard makes it one undecidable segment naming that guard,
            and it resolves to ASK
        """
        cmd = "if [ -f x ]; then echo a; else echo b; fi"
        self.assertEqual(
            _extracted(cmd),
            [
                (
                    "undecidable",
                    "if statement with else/elif cannot be statically decomposed",
                )
            ],
        )
        self.assertEqual(_resolve(cmd, ["echo:*"], []), "ask")

    def test_case_statement_asks(self):
        """
        Given allow `echo:*`
        When a one-line `case ... esac` statement is resolved
        Then the GRAMMAR REJECTS IT -- the undecidable segment reads "command did not
            parse", not the extractor's case-statement reason -- and it resolves to ASK

        CHARACTERIZATION, pinning a known defect: proposed ticket 19's P7 says a
        one-line `case` does not parse at all, so `_structured_from_ir_element`'s
        `CASE_STMT` branch is unreachable from here and untested by this file.
        Do not relax this to a bare `assertEqual(..., "ask")`: ASK is also what a
        plain parse failure produces, which is what made this test unfalsifiable
        before. When the grammar learns `case`, this SHOULD fail -- that is the point.
        """
        cmd = "case $x in a) echo hi;; esac"
        self.assertEqual(
            _extracted(cmd),
            [("undecidable", "command did not parse; cannot safely decompose")],
        )
        self.assertEqual(_resolve(cmd, ["echo:*"], []), "ask")

    def test_foreign_node_inline_code_asks(self):
        """
        Given allow `node -e:*`
        When `node -e "..."` carries inline JavaScript
        Then it is one ask_floor leaf and resolves to ASK (allow cannot downgrade it)
        """
        cmd = 'node -e "process.exit(0)"'
        self.assertEqual(_extracted(cmd), [("leaf", cmd, True)])
        self.assertEqual(_resolve(cmd, ["node -e:*"], []), "ask")


class TestQuoteRobustness(unittest.TestCase):
    """Escaped/closed quotes must not let a hidden statement leak out of a quoted argument."""

    def test_escaped_double_quote_does_not_split_statement(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo "a\\"b; rm -rf /"` has an escaped quote before a `; rm -rf /` inside the string
        Then the escaped quote does not close the string, the whole thing stays ONE leaf,
            and the compound is ALLOWED
        """
        cmd = r'echo "a\"b; rm -rf /"'
        self.assertEqual(_extracted(cmd), [("leaf", cmd, False)])
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "allow")

    def test_single_quote_idiom_does_not_split_statement(self):
        """
        Given allow `echo:*` and deny `rm -rf:*`
        When `echo 'a'\\''b; rm -rf /'` uses the `'\\''` single-quote idiom around a `; rm -rf /`
        Then the content stays a single quoted argument in one leaf and the compound is ALLOWED
        """
        cmd = r"echo 'a'\''b; rm -rf /'"
        self.assertEqual(_extracted(cmd), [("leaf", cmd, False)])
        self.assertEqual(_resolve(cmd, ["echo:*"], ["rm -rf:*"]), "allow")


class TestForeignInterpreterVersionRobustness(unittest.TestCase):
    """Versioned interpreters are recognized dynamically (no hard-coded version list)."""

    def test_future_python_minor_version_inline_code_is_floored(self):
        """
        Given allow `python3.14 -c:*` (a Python version not enumerated anywhere)
        When `python3.14 -c "..."` runs inline code
        Then the leaf carries ask_floor and resolves to ASK (allow can't downgrade it)
        """
        cmd = 'python3.14 -c "import os"'
        self.assertEqual(_extracted(cmd), [("leaf", cmd, True)])
        self.assertEqual(_resolve(cmd, ["python3.14 -c:*"], []), "ask")

    def test_arbitrary_python_minor_version_inline_code_is_floored(self):
        """
        Given allow `python3.99 -c:*`
        When an arbitrary far-future Python minor version runs inline code
        Then the leaf carries ask_floor and resolves to ASK (prefix recognition, not a
            maintained version list)
        """
        cmd = 'python3.99 -c "x"'
        self.assertEqual(_extracted(cmd), [("leaf", cmd, True)])
        self.assertEqual(_resolve(cmd, ["python3.99 -c:*"], []), "ask")

    def test_heredoc_into_versioned_python_asks(self):
        """
        Given allow `python3.13:*`
        When a heredoc is fed to `python3.13` (a versioned interpreter)
        Then the sentinel names the versioned sink, carries ask_floor, and the compound
            resolves to ASK
        """
        cmd = "python3.13 - <<'PY'\nx\nPY"
        self.assertEqual(
            _extracted(cmd),
            [("leaf", "python3.13 - __HEREDOC_TO_python3_13__", True)],
        )
        self.assertEqual(_resolve(cmd, ["python3.13:*"], []), "ask")


if __name__ == "__main__":
    unittest.main()
