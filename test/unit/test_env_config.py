"""
Unit tests for toolguard environment configuration.

Tests environment variable loading, .env file parsing, and configuration merging.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.env_config import find_project_root, get_bool_env, get_env_config, load_env_file


class TestFindProjectRoot(unittest.TestCase):
    """Test project root detection."""

    def test_finds_git_directory(self):
        """Test finding project root with .git directory."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            subdir = project_dir / 'subdir'
            subdir.mkdir()

            # Should find project_dir from subdir
            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)

    def test_finds_pyproject_toml(self):
        """Test finding project root with pyproject.toml."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / 'pyproject.toml').touch()
            subdir = project_dir / 'subdir' / 'deep'
            subdir.mkdir(parents=True)

            # Should find project_dir from deep subdir
            result = find_project_root(subdir)
            self.assertEqual(result, project_dir)

    def test_returns_none_when_not_found(self):
        """Test that None is returned when no project root found."""
        with TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / 'no_project'
            test_dir.mkdir()

            # Should return None
            result = find_project_root(test_dir)
            self.assertIsNone(result)

    def test_prefers_git_over_pyproject(self):
        """Test that .git is found at same level as pyproject.toml."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            (project_dir / 'pyproject.toml').touch()

            # Should find project_dir (with .git taking precedence)
            result = find_project_root(project_dir)
            self.assertEqual(result, project_dir)

    def test_stops_at_home_directory(self):
        """Test that search stops at home directory."""
        # Create a temp dir that's NOT under home
        with TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / 'test'
            test_dir.mkdir()

            # Mock Path.home() to return a directory we control
            with patch('pathlib.Path.home') as mock_home:
                mock_home.return_value = Path(tmpdir)

                # Should return None (stopped at mock home)
                result = find_project_root(test_dir)
                self.assertIsNone(result)


class TestLoadEnvFile(unittest.TestCase):
    """Test .env file loading."""

    def test_load_basic_env_file(self):
        """Test loading basic .env file with dotenv."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('KEY1=value1\nKEY2=value2\n')

            result = load_env_file(project_root)

            self.assertEqual(result.get('KEY1'), 'value1')
            self.assertEqual(result.get('KEY2'), 'value2')

    def test_load_with_source_root(self):
        """Test loading .env from source root subdirectory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / 'src'
            src_dir.mkdir()
            env_file = src_dir / '.env'
            env_file.write_text('SOURCE_VAR=from_src\n')

            result = load_env_file(project_root, 'src')

            self.assertEqual(result.get('SOURCE_VAR'), 'from_src')

    def test_load_nonexistent_file_returns_empty(self):
        """Test that loading nonexistent .env returns empty dict."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = load_env_file(project_root)

            self.assertEqual(result, {})

    def test_load_handles_comments(self):
        """Test that comments are ignored in .env file."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('# Comment\nKEY=value\n# Another comment\n')

            result = load_env_file(project_root)

            self.assertEqual(result.get('KEY'), 'value')
            self.assertNotIn('# Comment', result)

    def test_load_handles_quotes(self):
        """Test that quoted values are unquoted."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('DOUBLE="value with spaces"\nSINGLE=\'another value\'\n')

            result = load_env_file(project_root)

            self.assertEqual(result.get('DOUBLE'), 'value with spaces')
            self.assertEqual(result.get('SINGLE'), 'another value')

    def test_load_handles_empty_lines(self):
        """Test that empty lines are ignored."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('\nKEY1=value1\n\n\nKEY2=value2\n\n')

            result = load_env_file(project_root)

            self.assertEqual(len(result), 2)
            self.assertEqual(result.get('KEY1'), 'value1')
            self.assertEqual(result.get('KEY2'), 'value2')


class TestGetBoolEnv(unittest.TestCase):
    """Test boolean environment variable parsing."""

    def test_parse_true_values(self):
        """Test parsing various true values."""
        test_cases = ['true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES']

        for value in test_cases:
            with patch.dict(os.environ, {'TEST_VAR': value}):
                result = get_bool_env('TEST_VAR', False)
                self.assertTrue(result, f'Failed for value: {value}')

    def test_parse_false_values(self):
        """Test parsing various false values."""
        test_cases = ['false', 'False', 'FALSE', '0', 'no', 'No', 'NO']

        for value in test_cases:
            with patch.dict(os.environ, {'TEST_VAR': value}):
                result = get_bool_env('TEST_VAR', True)
                self.assertFalse(result, f'Failed for value: {value}')

    def test_fallback_to_env_vars_dict(self):
        """Test fallback to env_vars dict when env not set."""
        env_vars = {'TEST_VAR': 'true'}

        result = get_bool_env('TEST_VAR', False, env_vars)

        self.assertTrue(result)

    def test_env_takes_precedence_over_dict(self):
        """Test that environment variable takes precedence."""
        env_vars = {'TEST_VAR': 'false'}

        with patch.dict(os.environ, {'TEST_VAR': 'true'}):
            result = get_bool_env('TEST_VAR', False, env_vars)

        self.assertTrue(result)

    def test_default_when_not_found(self):
        """Test using default when variable not found."""
        result_true = get_bool_env('NONEXISTENT', True)
        result_false = get_bool_env('NONEXISTENT', False)

        self.assertTrue(result_true)
        self.assertFalse(result_false)

    def test_invalid_value_uses_default(self):
        """Test that invalid boolean value uses default."""
        with patch.dict(os.environ, {'TEST_VAR': 'maybe'}):
            result = get_bool_env('TEST_VAR', True)

        self.assertTrue(result)


class TestGetEnvConfig(unittest.TestCase):
    """Test complete environment configuration loading."""

    def test_default_config(self):
        """Test default configuration values."""
        with TemporaryDirectory() as tmpdir:
            with patch('toolguard.env_config.find_project_root') as mock_find:
                mock_find.return_value = Path(tmpdir)

                config = get_env_config()

                self.assertTrue(config['logging_enabled'])
                self.assertTrue(config['extended_syntax'])
                self.assertFalse(config['create_log_dir'])
                # Resolve both paths for comparison (handles macOS /private/var vs /var symlink)
                self.assertEqual(config['log_dir'], (Path(tmpdir) / 'logs').resolve())
                self.assertEqual(config['project_root'], Path(tmpdir))
                self.assertEqual(config['source_root'], '')

    def test_explicit_project_root(self):
        """Test using explicit TOOLGUARD_PROJECT_ROOT."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_PROJECT_ROOT': tmpdir}):
                config = get_env_config()

                self.assertEqual(config['project_root'], Path(tmpdir).resolve())

    def test_explicit_log_dir_absolute(self):
        """Test using explicit absolute TOOLGUARD_LOG_DIR."""
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / 'mylogs'
            with patch.dict(os.environ, {'TOOLGUARD_LOG_DIR': str(log_dir)}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    # Resolve both paths for comparison (handles macOS /private/var vs /var symlink)
                    self.assertEqual(config['log_dir'], log_dir.resolve())

    def test_explicit_log_dir_relative(self):
        """Test using explicit relative TOOLGUARD_LOG_DIR."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_LOG_DIR': 'custom/logs'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    expected = (Path(tmpdir) / 'custom' / 'logs').resolve()
                    self.assertEqual(config['log_dir'], expected)

    def test_disable_logging(self):
        """Test disabling logging via TOOLGUARD_LOGGING_ENABLED."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_LOGGING_ENABLED': 'false'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertFalse(config['logging_enabled'])

    def test_disable_extended_syntax(self):
        """Test disabling extended syntax via TOOLGUARD_EXTENDED_SYNTAX."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_EXTENDED_SYNTAX': 'false'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertFalse(config['extended_syntax'])

    def test_enable_create_log_dir(self):
        """Test enabling log directory creation."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_CREATE_LOG_DIR': 'true'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertTrue(config['create_log_dir'])

    def test_source_root_configuration(self):
        """Test TOOLGUARD_SOURCE_ROOT configuration."""
        with TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'TOOLGUARD_SOURCE_ROOT': 'src'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = Path(tmpdir)

                    config = get_env_config()

                    self.assertEqual(config['source_root'], 'src')

    def test_loads_from_env_file(self):
        """Test loading configuration from .env file."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('TOOLGUARD_LOGGING_ENABLED=false\nTOOLGUARD_EXTENDED_SYNTAX=false\n')

            with patch('toolguard.env_config.find_project_root') as mock_find:
                mock_find.return_value = project_root

                config = get_env_config()

                self.assertFalse(config['logging_enabled'])
                self.assertFalse(config['extended_syntax'])

    def test_env_overrides_env_file(self):
        """Test that environment variables override .env file."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            env_file = project_root / '.env'
            env_file.write_text('TOOLGUARD_LOGGING_ENABLED=false\n')

            with patch.dict(os.environ, {'TOOLGUARD_LOGGING_ENABLED': 'true'}):
                with patch('toolguard.env_config.find_project_root') as mock_find:
                    mock_find.return_value = project_root

                    config = get_env_config()

                    self.assertTrue(config['logging_enabled'])

    def test_no_project_root_uses_cwd(self):
        """Test that current directory is used when no project root found."""
        with patch('toolguard.env_config.find_project_root') as mock_find:
            mock_find.return_value = None

            config = get_env_config()

            self.assertEqual(config['project_root'], Path.cwd())


if __name__ == '__main__':
    unittest.main()
