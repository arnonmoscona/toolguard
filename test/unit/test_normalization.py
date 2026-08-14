"""Unit tests for path normalization."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.normalization import normalize_path, expand_tilde, normalize_command


def _symlink_or_skip(case: unittest.TestCase, link: Path, target: Path) -> None:
    """Create link -> target, skipping the test where symlinks are unsupported."""
    try:
        link.symlink_to(target)
    except OSError:
        case.skipTest("Symlink creation not supported")


class TestNormalizePath(unittest.TestCase):
    """Test normalize_path function."""

    def setUp(self):
        """Set up test fixtures."""
        self.home = Path.home()
        # Resolved, so an assertion can compare against an exact string even where the
        # temp root itself is a symlink (macOS /tmp).
        self.project_root = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_normalize_home_path(self):
        """
        Given an absolute path located under the user's home directory
        When normalize_path is applied to it
        Then the home prefix is collapsed to '~/projects/file.txt'
        """
        path = str(self.home / "projects" / "file.txt")
        result = normalize_path(path)
        self.assertEqual(result, "~/projects/file.txt")

    def test_normalize_multiple_leading_slashes(self):
        """
        Given absolute paths with two, three, or four leading slashes
        When normalize_path is applied to each
        Then the leading slashes collapse to a single '/tmp/file'
        """
        self.assertEqual(normalize_path("//tmp/file"), "/tmp/file")
        self.assertEqual(normalize_path("///tmp/file"), "/tmp/file")
        self.assertEqual(normalize_path("////tmp/file"), "/tmp/file")

    def test_normalize_relative_path_without_project_root(self):
        """
        Given a bare relative filename and no project root
        When normalize_path is applied
        Then the path receives a './' prefix ('./file.txt') whether or not it exists
        """
        self.assertEqual(normalize_path("file.txt"), "./file.txt")
        self.assertEqual(
            normalize_path("no_such_file_anywhere.txt"), "./no_such_file_anywhere.txt"
        )

    def test_normalize_relative_path_with_project_root(self):
        """
        Given a project root under which one name exists and another does not
        When normalize_path is applied to each with that project root
        Then only the existing name receives a './' prefix; the missing one is left bare

        The existence gate is the only thing project_root does, so the negative case is
        what makes the parameter observable at all. Characterisation: the same relative
        path normalizes to two different canonical forms depending on whether a caller
        passes project_root -- see proposed-ticket queue row 13.
        """
        (self.project_root / "test.txt").touch()

        self.assertEqual(normalize_path("test.txt", self.project_root), "./test.txt")
        self.assertEqual(
            normalize_path("missing.txt", self.project_root), "missing.txt"
        )

    def test_normalize_absolute_path_outside_home(self):
        """
        Given an absolute path outside the home directory ('/tmp/file.txt')
        When normalize_path is applied
        Then the path is returned unchanged
        """
        result = normalize_path("/tmp/file.txt")
        self.assertEqual(result, "/tmp/file.txt")

    def test_normalize_already_normalized_relative(self):
        """
        Given a relative path that already carries a './' prefix
        When normalize_path is applied
        Then the path is returned unchanged ('./file.txt')
        """
        result = normalize_path("./file.txt")
        self.assertEqual(result, "./file.txt")

    def test_normalize_already_normalized_tilde(self):
        """
        Given a path that already carries a '~' home prefix
        When normalize_path is applied
        Then the path is returned unchanged ('~/projects/file.txt')
        """
        result = normalize_path("~/projects/file.txt")
        self.assertEqual(result, "~/projects/file.txt")

    def test_normalize_empty_string(self):
        """
        Given an empty string
        When normalize_path is applied
        Then an empty string is returned
        """
        result = normalize_path("")
        self.assertEqual(result, "")

    def test_normalize_nonexistent_path(self):
        """
        Given a nonexistent path located under the home directory
        When normalize_path is applied
        Then the format is still normalized to '~/nonexistent/file.txt'
        """
        path = str(self.home / "nonexistent" / "file.txt")
        result = normalize_path(path)
        self.assertEqual(result, "~/nonexistent/file.txt")

    def test_normalize_root_path(self):
        """
        Given the root path, written as '/' and as '//'
        When normalize_path is applied
        Then both collapse to '/'
        """
        self.assertEqual(normalize_path("/"), "/")
        self.assertEqual(normalize_path("//"), "/")

    def test_normalize_current_dir(self):
        """
        Given the current-directory token ('.')
        When normalize_path is applied
        Then it is returned unchanged -- a leading '.' skips the './' prefixing branch
        """
        result = normalize_path(".")
        self.assertEqual(result, ".")


class TestNormalizePathSymlinkResolution(unittest.TestCase):
    """normalize_path's symlink step, over a temp tree that no home prefix can reach."""

    def setUp(self):
        """Build a temp tree and point Path.home() at a sibling of it.

        The patched home is insulation, not the subject: it keeps the home-collapse step
        out of these assertions where TMPDIR happens to live under $HOME, which otherwise
        rewrites every expected path to a '~/' form and fails the class.
        """
        self.root = Path(tempfile.mkdtemp(prefix="tg_symlinks_")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        elsewhere = Path(tempfile.mkdtemp(prefix="tg_not_home_")).resolve()
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)
        patcher = patch.object(Path, "home", return_value=elsewhere)
        self.home_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_normalize_symlink(self):
        """
        Given a symlink pointing at an existing target file
        When normalize_path is applied to the symlink path
        Then the result is exactly the target path, not the link's own spelling
        """
        target_file = self.root / "target.txt"
        target_file.touch()
        symlink_path = self.root / "link.txt"
        _symlink_or_skip(self, symlink_path, target_file)

        result = normalize_path(str(symlink_path))

        self.assertTrue(self.home_mock.called)
        self.assertEqual(result, str(target_file))
        self.assertNotEqual(result, str(symlink_path))

    def test_normalize_symlink_chain(self):
        """
        Given a three-link symlink chain ending at an existing file
        When normalize_path is applied to the outermost link
        Then the whole chain is followed and the final target is returned
        """
        target_file = self.root / "target.txt"
        target_file.touch()
        first = self.root / "a"
        second = self.root / "b"
        third = self.root / "c"
        _symlink_or_skip(self, first, target_file)
        _symlink_or_skip(self, second, first)
        _symlink_or_skip(self, third, second)

        self.assertEqual(normalize_path(str(third)), str(target_file))

    def test_normalize_dangling_symlink_agrees_with_its_target(self):
        """
        Given a symlink whose target does not exist yet
        When normalize_path is applied to the link and to the target path
        Then both spellings of that location normalize to the same string

        RED, and deliberately so: proposed ticket 48. The symlink step is gated on
        exists(), which follows the link, so a dangling link keeps its own spelling and a
        deny rule naming the target does not fire -- while writing through the link
        (cp, >, tee) creates that very target.
        """
        target_file = self.root / "not_yet.txt"
        dangling = self.root / "dangling_link"
        _symlink_or_skip(self, dangling, target_file)

        self.assertEqual(
            normalize_path(str(dangling)), normalize_path(str(target_file))
        )

    def test_normalize_path_under_a_symlinked_directory_agrees_with_the_real_path(self):
        """
        Given an existing file reachable both through a symlinked parent directory and
            through the real directory
        When normalize_path is applied to each spelling
        Then both normalize to the same string

        RED. Same bypass class as the dangling-link case above, and it needs no dangling
        link at all: the symlink step resolves only a path that IS a symlink, never one
        whose parent is, so '<dir_link>/f.txt' never reaches '<real_dir>/f.txt'. Fixing it
        is a wider change than ticket 48's -- it moves every path under a symlinked
        directory -- so this one is a decision, not an obvious repair.
        """
        real_dir = self.root / "realdir"
        real_dir.mkdir()
        real_file = real_dir / "f.txt"
        real_file.touch()
        dir_link = self.root / "dirlink"
        _symlink_or_skip(self, dir_link, real_dir)

        self.assertEqual(
            normalize_path(str(dir_link / "f.txt")), normalize_path(str(real_file))
        )


class TestNormalizePathAgainstAPatchedHome(unittest.TestCase):
    """normalize_path's home-collapse step, with a temp directory standing in for $HOME."""

    def setUp(self):
        """Point Path.home() at a temporary directory for the duration of the test."""
        self.fake_home = Path(tempfile.mkdtemp(prefix="tg_fake_home_")).resolve()
        self.addCleanup(shutil.rmtree, self.fake_home, ignore_errors=True)
        patcher = patch.object(Path, "home", return_value=self.fake_home)
        self.home_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_path_under_the_patched_home_collapses_to_tilde(self):
        """
        Given Path.home() patched to a temporary directory
        When normalize_path is applied to a path under that directory
        Then it collapses to '~/x.txt', which proves the patched home is what was consulted
        """
        result = normalize_path(str(self.fake_home / "x.txt"))

        self.assertEqual(result, "~/x.txt")
        self.assertTrue(self.home_mock.called)

    def test_the_home_directory_itself_normalizes_to_the_same_spelling_as_tilde(self):
        """
        Given the home directory named by its absolute path and by '~'
        When normalize_path is applied to each
        Then both produce the same canonical spelling

        RED, and deliberately so. The absolute form yields '~/.' -- Path.relative_to()
        returns Path('.') for the home directory itself and the f-string keeps it -- while
        '~' is returned untouched. Two spellings of one location, two canonical forms, and
        '~/.' is not a form any rule author writes.
        """
        result = normalize_path(str(self.fake_home))

        self.assertTrue(self.home_mock.called)
        self.assertEqual(result, normalize_path("~"))

    def test_a_symlink_under_home_is_resolved_before_the_home_prefix_is_applied(self):
        """
        Given a symlink under home pointing at another file under home
        When normalize_path is applied to the link
        Then the result is the target's '~/' form, not the link's

        Pins the order of the two steps: collapsing the home prefix first would leave
        '~/link.txt' and the link would never be followed.
        """
        target = self.fake_home / "target.txt"
        target.touch()
        link = self.fake_home / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation not supported")

        result = normalize_path(str(link))

        self.assertEqual(result, "~/target.txt")
        self.assertTrue(self.home_mock.called)


class TestExpandTilde(unittest.TestCase):
    """Test expand_tilde function."""

    def test_expand_tilde_home(self):
        """
        Given a bare tilde ('~')
        When expand_tilde is applied
        Then it is expanded to the absolute home directory path
        """
        result = expand_tilde("~")
        self.assertEqual(result, str(Path.home()))

    def test_expand_tilde_with_path(self):
        """
        Given a tilde-prefixed path ('~/projects/file.txt')
        When expand_tilde is applied
        Then the tilde expands to home and the suffix is preserved
        """
        result = expand_tilde("~/projects/file.txt")
        expected = str(Path.home()) + "/projects/file.txt"
        self.assertEqual(result, expected)

    def test_expand_tilde_no_tilde(self):
        """
        Given an absolute path without a tilde ('/tmp/file.txt')
        When expand_tilde is applied
        Then the path is returned unchanged
        """
        result = expand_tilde("/tmp/file.txt")
        self.assertEqual(result, "/tmp/file.txt")

    def test_expand_tilde_empty_string(self):
        """
        Given an empty string
        When expand_tilde is applied
        Then an empty string is returned
        """
        result = expand_tilde("")
        self.assertEqual(result, "")

    def test_expand_tilde_glob_pattern(self):
        """
        Given a tilde-prefixed glob pattern ('~/projects/*.py')
        When expand_tilde is applied
        Then the tilde expands to home while the glob wildcard is preserved
        """
        result = expand_tilde("~/projects/*.py")
        expected = str(Path.home()) + "/projects/*.py"
        self.assertEqual(result, expected)

    def test_expand_tilde_other_users_home_is_left_alone(self):
        """
        Given a '~username' form and a doubled tilde
        When expand_tilde is applied
        Then both are returned unchanged -- only '~' and '~/...' are expanded
        """
        self.assertEqual(expand_tilde("~root"), "~root")
        self.assertEqual(expand_tilde("~root/.ssh"), "~root/.ssh")
        self.assertEqual(expand_tilde("~~"), "~~")


class TestNormalizeCommand(unittest.TestCase):
    """Test normalize_command function."""

    def setUp(self):
        """Set up test fixtures."""
        self.home = Path.home()
        self.project_root = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_normalize_command_with_home_path(self):
        """
        Given a command whose argument is an absolute path under home ('cat <home>/file.txt')
        When normalize_command is applied
        Then the home path is collapsed to '~' ('cat ~/file.txt')
        """
        path = str(self.home / "file.txt")
        command = f"cat {path}"
        result = normalize_command(command)
        self.assertEqual(result, "cat ~/file.txt")

    def test_normalize_command_with_multiple_slashes(self):
        """
        Given a command with a multi-slash absolute path argument
        When normalize_command is applied
        Then the leading slashes collapse ('ls /tmp/toolguard_absent_file')

        The path names a file that does not exist, so no symlink resolution can vary the
        answer per machine (on macOS '/tmp' itself is a symlink, but its children are not).
        """
        result = normalize_command("ls //tmp/toolguard_absent_file")
        self.assertEqual(result, "ls /tmp/toolguard_absent_file")

    def test_normalize_command_no_paths(self):
        """
        Given a command with no path arguments ('echo hello world')
        When normalize_command is applied
        Then the command is returned unchanged
        """
        result = normalize_command("echo hello world")
        self.assertEqual(result, "echo hello world")

    def test_normalize_command_multiple_paths(self):
        """
        Given a command with two absolute home-path arguments ('cp <home>/f1 <home>/f2')
        When normalize_command is applied
        Then both arguments collapse to '~' ('cp ~/file1.txt ~/file2.txt')
        """
        path1 = str(self.home / "file1.txt")
        path2 = str(self.home / "file2.txt")
        command = f"cp {path1} {path2}"
        result = normalize_command(command)
        self.assertEqual(result, "cp ~/file1.txt ~/file2.txt")

    def test_normalize_command_empty_string(self):
        """
        Given an empty command string
        When normalize_command is applied
        Then an empty string is returned
        """
        result = normalize_command("")
        self.assertEqual(result, "")

    def test_normalize_command_with_flags(self):
        """
        Given a command with flags plus a home-path argument ('ls -la <home>/dir')
        When normalize_command is applied
        Then flags are preserved and the path collapses to '~' ('ls -la ~/dir')
        """
        path = str(self.home / "dir")
        command = f"ls -la {path}"
        result = normalize_command(command)
        self.assertEqual(result, "ls -la ~/dir")

    def test_normalize_command_path_bearing_flags_are_left_alone(self):
        """
        Given flags whose own text is path-shaped ('-I/usr/include', '--out=notes.txt')
        When normalize_command is applied
        Then they are preserved verbatim

        A plain '-la' cannot show that the leading-'-' branch does anything: it reaches
        neither the slash test nor the extension heuristic, so it survives either way.
        """
        result = normalize_command("gcc -I/usr/include --out=notes.txt main.c")
        self.assertEqual(result, "gcc -I/usr/include --out=notes.txt ./main.c")

    def test_normalize_command_relative_path(self):
        """
        Given a command with a bare relative-file argument ('cat file.txt')
        When normalize_command is applied
        Then the argument receives a './' prefix ('cat ./file.txt')
        """
        result = normalize_command("cat file.txt")
        self.assertEqual(result, "cat ./file.txt")

    def test_normalize_command_long_extension_is_not_a_path(self):
        """
        Given argument tokens whose suffix after the last dot is longer than four
            characters, or not alphanumeric
        When normalize_command is applied
        Then they are not treated as paths and keep their spelling

        The negative half of the extension heuristic; without it nothing distinguishes the
        heuristic from 'any token containing a dot is a path'.
        """
        self.assertEqual(
            normalize_command("echo notes.markdown"), "echo notes.markdown"
        )
        self.assertEqual(normalize_command("echo a.t_x"), "echo a.t_x")

    def test_normalize_command_already_normalized(self):
        """
        Given a command whose path argument is already tilde-normalized ('cat ~/file.txt')
        When normalize_command is applied
        Then the command is returned unchanged
        """
        result = normalize_command("cat ~/file.txt")
        self.assertEqual(result, "cat ~/file.txt")

    def test_normalize_command_mixed_paths(self):
        """
        Given a command mixing an absolute home path and a relative path ('diff <home>/abs.txt rel.txt')
        When normalize_command is applied
        Then the home path collapses to '~' and the relative path gains './' ('diff ~/abs.txt ./rel.txt')
        """
        path = str(self.home / "abs.txt")
        command = f"diff {path} rel.txt"
        result = normalize_command(command)
        self.assertEqual(result, "diff ~/abs.txt ./rel.txt")

    def test_normalize_command_is_a_relative_path(self):
        """
        Given a command whose first token is a relative path ('bin/script.sh')
        When normalize_command is applied
        Then the first token gains a './' prefix ('./bin/script.sh')
        """
        self.assertEqual(normalize_command("bin/script.sh"), "./bin/script.sh")

    def test_normalize_command_already_dot_slash(self):
        """
        Given a command whose first token already has a './' prefix ('./bin/script.sh')
        When normalize_command is applied
        Then the first token is preserved unchanged
        """
        self.assertEqual(normalize_command("./bin/script.sh"), "./bin/script.sh")

    def test_normalize_command_relative_path_with_args_and_flag(self):
        """
        Given a relative first-token command with a flag and a relative arg ('bin/script.sh --verbose other.txt')
        When normalize_command is applied
        Then the first token and the relative arg gain './' while the flag is preserved
        """
        result = normalize_command("bin/script.sh --verbose other.txt")
        self.assertEqual(result, "./bin/script.sh --verbose ./other.txt")

    def test_normalize_command_bare_command_name_unchanged(self):
        """
        Given commands whose first token is a bare name with no slash ('ls', 'git status', 'python')
        When normalize_command is applied
        Then the bare names are NOT treated as paths and are returned unchanged
        """
        self.assertEqual(normalize_command("ls"), "ls")
        self.assertEqual(normalize_command("git status"), "git status")
        self.assertEqual(normalize_command("python"), "python")

    def test_normalize_command_absolute_first_token_under_home(self):
        """
        Given a command whose first token is an absolute path under home
        When normalize_command is applied
        Then the first token collapses to '~'

        The directory is one that exists on no machine: the previous fixture used
        '<home>/bin', which on this developer's machine is a symlink, so the test's answer
        depended on the home layout of whoever ran it.
        """
        path = str(self.home / "tg_no_such_dir" / "myscript")
        self.assertEqual(normalize_command(path), "~/tg_no_such_dir/myscript")

    def test_normalize_command_forwards_the_project_root(self):
        """
        Given a project root under which one argument exists and another does not
        When normalize_command is applied with that project root
        Then only the existing argument gains './', which is observable only if the root
            reaches normalize_path
        """
        (self.project_root / "there.txt").touch()

        self.assertEqual(
            normalize_command("cat there.txt", self.project_root), "cat ./there.txt"
        )
        self.assertEqual(
            normalize_command("cat missing.txt", self.project_root), "cat missing.txt"
        )

    def test_normalize_command_collapses_runs_of_whitespace_and_newlines(self):
        """
        Given commands separated by repeated spaces or by a newline
        When normalize_command is applied
        Then every run of whitespace becomes a single space

        Characterisation of a lossy step, not an endorsement: the normalized variant of a
        multi-line command has had its newlines removed, and permissions.match_command is
        safe from that only because it computes its newline guard from the raw string
        first.
        """
        self.assertEqual(normalize_command("echo  a   b"), "echo a b")
        self.assertEqual(normalize_command("echo a\nb"), "echo a b")


if __name__ == "__main__":
    unittest.main()
