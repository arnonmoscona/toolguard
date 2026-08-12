"""Unit tests for path normalization."""

import unittest
from pathlib import Path
import tempfile
from toolguard.normalization import normalize_path, expand_tilde, normalize_command


class TestNormalizePath(unittest.TestCase):
    """Test normalize_path function."""

    def setUp(self):
        """Set up test fixtures."""
        self.home = Path.home()
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

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
        Then the path receives a './' prefix ('./file.txt')
        """
        result = normalize_path("file.txt")
        self.assertEqual(result, "./file.txt")

    def test_normalize_relative_path_with_project_root(self):
        """
        Given an existing file under a supplied project root
        When normalize_path is applied with that project root
        Then the path is normalized relative to the root as './test.txt'
        """
        test_file = self.project_root / "test.txt"
        test_file.touch()

        result = normalize_path("test.txt", self.project_root)
        self.assertEqual(result, "./test.txt")

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

    def test_normalize_symlink(self):
        """
        Given a symlink pointing at an existing target file
        When normalize_path is applied to the symlink path
        Then the result resolves to the target ('target.txt' appears in it),
            or the test is skipped if symlinks are unsupported
        """
        target_file = self.project_root / "target.txt"
        target_file.touch()
        symlink_path = self.project_root / "link.txt"

        try:
            symlink_path.symlink_to(target_file)
            result = normalize_path(str(symlink_path))
            self.assertIn("target.txt", result)
        except OSError:
            self.skipTest("Symlink creation not supported")

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
        Given the root path ('/')
        When normalize_path is applied
        Then the root path is returned unchanged
        """
        result = normalize_path("/")
        self.assertEqual(result, "/")

    def test_normalize_current_dir(self):
        """
        Given the current-directory token ('.')
        When normalize_path is applied
        Then the result begins with '.' (it stays a relative reference)
        """
        result = normalize_path(".")
        self.assertTrue(result.startswith("."))


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


class TestNormalizeCommand(unittest.TestCase):
    """Test normalize_command function."""

    def setUp(self):
        """Set up test fixtures."""
        self.home = Path.home()

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
        Given a command with a multi-slash path argument ('ls //tmp')
        When normalize_command is applied
        Then the slashes collapse to '/tmp' (or the macOS '/private/tmp' symlink target)
        """
        result = normalize_command("ls //tmp")
        self.assertIn(result, ["ls /tmp", "ls /private/tmp"])

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

    def test_normalize_command_relative_path(self):
        """
        Given a command with a bare relative-file argument ('cat file.txt')
        When normalize_command is applied
        Then the argument receives a './' prefix ('cat ./file.txt')
        """
        result = normalize_command("cat file.txt")
        self.assertEqual(result, "cat ./file.txt")

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
        Given a command whose first token is an absolute path under home ('<home>/bin/myscript')
        When normalize_command is applied
        Then the first token collapses to '~' ('~/bin/myscript')
        """
        path = str(self.home / "bin" / "myscript")
        self.assertEqual(normalize_command(path), "~/bin/myscript")


if __name__ == "__main__":
    unittest.main()
