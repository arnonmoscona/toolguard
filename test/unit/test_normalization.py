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
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_home_path(self):
        """Test converting /Users/<username> to ~."""
        path = str(self.home / 'projects' / 'file.txt')
        result = normalize_path(path)
        self.assertEqual(result, '~/projects/file.txt')

    def test_normalize_multiple_leading_slashes(self):
        """Test normalizing multiple leading slashes."""
        self.assertEqual(normalize_path('//tmp/file'), '/tmp/file')
        self.assertEqual(normalize_path('///tmp/file'), '/tmp/file')
        self.assertEqual(normalize_path('////tmp/file'), '/tmp/file')

    def test_normalize_relative_path_without_project_root(self):
        """Test relative path normalization without project root."""
        result = normalize_path('file.txt')
        self.assertEqual(result, './file.txt')

    def test_normalize_relative_path_with_project_root(self):
        """Test relative path normalization with project root."""
        # Create a file in temp dir
        test_file = self.project_root / 'test.txt'
        test_file.touch()

        result = normalize_path('test.txt', self.project_root)
        self.assertEqual(result, './test.txt')

    def test_normalize_absolute_path_outside_home(self):
        """Test absolute path outside home directory."""
        result = normalize_path('/tmp/file.txt')
        self.assertEqual(result, '/tmp/file.txt')

    def test_normalize_already_normalized_relative(self):
        """Test path that already has ./ prefix."""
        result = normalize_path('./file.txt')
        self.assertEqual(result, './file.txt')

    def test_normalize_already_normalized_tilde(self):
        """Test path that already has ~ prefix."""
        result = normalize_path('~/projects/file.txt')
        self.assertEqual(result, '~/projects/file.txt')

    def test_normalize_empty_string(self):
        """Test empty string handling."""
        result = normalize_path('')
        self.assertEqual(result, '')

    def test_normalize_symlink(self):
        """Test symlink resolution."""
        # Create a file and a symlink to it
        target_file = self.project_root / 'target.txt'
        target_file.touch()
        symlink_path = self.project_root / 'link.txt'

        try:
            symlink_path.symlink_to(target_file)

            # Normalize the symlink path
            result = normalize_path(str(symlink_path))

            # The result should be the resolved target
            # (may be under home, so could be ~ prefixed)
            self.assertIn('target.txt', result)
        except OSError:
            # Symlink creation might fail on some systems
            self.skipTest('Symlink creation not supported')

    def test_normalize_nonexistent_path(self):
        """Test normalization of nonexistent path."""
        # Should still normalize format even if path doesn't exist
        path = str(self.home / 'nonexistent' / 'file.txt')
        result = normalize_path(path)
        self.assertEqual(result, '~/nonexistent/file.txt')

    def test_normalize_root_path(self):
        """Test normalization of root path."""
        result = normalize_path('/')
        self.assertEqual(result, '/')

    def test_normalize_current_dir(self):
        """Test normalization of current directory."""
        result = normalize_path('.')
        # Current directory should get ./ prefix if relative
        self.assertTrue(result.startswith('.'))


class TestExpandTilde(unittest.TestCase):
    """Test expand_tilde function."""

    def test_expand_tilde_home(self):
        """Test expanding ~ to home directory."""
        result = expand_tilde('~')
        self.assertEqual(result, str(Path.home()))

    def test_expand_tilde_with_path(self):
        """Test expanding ~/path to home/path."""
        result = expand_tilde('~/projects/file.txt')
        expected = str(Path.home()) + '/projects/file.txt'
        self.assertEqual(result, expected)

    def test_expand_tilde_no_tilde(self):
        """Test path without tilde remains unchanged."""
        result = expand_tilde('/tmp/file.txt')
        self.assertEqual(result, '/tmp/file.txt')

    def test_expand_tilde_empty_string(self):
        """Test empty string handling."""
        result = expand_tilde('')
        self.assertEqual(result, '')

    def test_expand_tilde_glob_pattern(self):
        """Test expanding tilde in glob pattern."""
        result = expand_tilde('~/projects/*.py')
        expected = str(Path.home()) + '/projects/*.py'
        self.assertEqual(result, expected)


class TestNormalizeCommand(unittest.TestCase):
    """Test normalize_command function."""

    def setUp(self):
        """Set up test fixtures."""
        self.home = Path.home()

    def test_normalize_command_with_home_path(self):
        """Test normalizing command with home path."""
        path = str(self.home / 'file.txt')
        command = f'cat {path}'
        result = normalize_command(command)
        self.assertEqual(result, 'cat ~/file.txt')

    def test_normalize_command_with_multiple_slashes(self):
        """Test normalizing command with multiple leading slashes."""
        result = normalize_command('ls //tmp')
        # On macOS, /tmp is a symlink to /private/tmp, so accept either
        self.assertIn(result, ['ls /tmp', 'ls /private/tmp'])

    def test_normalize_command_no_paths(self):
        """Test command with no paths remains unchanged."""
        result = normalize_command('echo hello world')
        self.assertEqual(result, 'echo hello world')

    def test_normalize_command_multiple_paths(self):
        """Test command with multiple paths."""
        path1 = str(self.home / 'file1.txt')
        path2 = str(self.home / 'file2.txt')
        command = f'cp {path1} {path2}'
        result = normalize_command(command)
        self.assertEqual(result, 'cp ~/file1.txt ~/file2.txt')

    def test_normalize_command_empty_string(self):
        """Test empty command string."""
        result = normalize_command('')
        self.assertEqual(result, '')

    def test_normalize_command_with_flags(self):
        """Test command with flags and paths."""
        path = str(self.home / 'dir')
        command = f'ls -la {path}'
        result = normalize_command(command)
        self.assertEqual(result, 'ls -la ~/dir')

    def test_normalize_command_relative_path(self):
        """Test command with relative path."""
        result = normalize_command('cat file.txt')
        self.assertEqual(result, 'cat ./file.txt')

    def test_normalize_command_already_normalized(self):
        """Test command with already normalized paths."""
        result = normalize_command('cat ~/file.txt')
        self.assertEqual(result, 'cat ~/file.txt')

    def test_normalize_command_mixed_paths(self):
        """Test command with mix of absolute and relative paths."""
        path = str(self.home / 'abs.txt')
        command = f'diff {path} rel.txt'
        result = normalize_command(command)
        self.assertEqual(result, 'diff ~/abs.txt ./rel.txt')


if __name__ == '__main__':
    unittest.main()
