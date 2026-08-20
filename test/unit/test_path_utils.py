"""
Unit tests for toolguard.path_utils: the path helpers that answer against
machine state supplied by toolguard.ambient.

A '~' is expanded against the ambient home rather than pathlib's, which reads
$HOME and then the passwd entry -- two routes no ambient binding governs.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import ambient
from toolguard.path_utils import expanduser


class TestExpanduserAnswersFromTheAmbientHome(unittest.TestCase):
    """
    expanduser reads home() for a leading bare '~', so overriding that fact
    governs it. A second read point would be a seam a test patches and silently
    never reaches.
    """

    def test_expanduser_resolves_a_tilde_through_the_home_accessor(self):
        """
        Given ambient.home patched and nothing else
        When expanduser() expands a path written with a leading '~'
        Then it lands under the patched home, so a '~' in configuration cannot
             route around a test that redirected home
        """
        with patch("toolguard.ambient.home", return_value=Path("/patched/home")):
            self.assertEqual(
                expanduser("~/.toolguard"), Path("/patched/home/.toolguard")
            )

    def test_expanduser_leaves_a_path_without_a_leading_tilde_alone(self):
        """
        Given a patched home
        When expanduser() is given an absolute path, a relative one, and another
             user's '~name' form
        Then none of them is rewritten to the patched home
        """
        with patch("toolguard.ambient.home", return_value=Path("/patched/home")):
            for raw, expected in (
                ("/abs/path", Path("/abs/path")),
                ("rel/path", Path("rel/path")),
                ("~root/x", Path("~root/x").expanduser()),
            ):
                with self.subTest(raw=raw):
                    self.assertEqual(expanduser(raw), expected)

    def test_a_bound_home_governs_tilde_expansion(self):
        """
        Given facts bound for the block, and a process $HOME pointing elsewhere
        When a '~' path is expanded through path_utils
        Then it lands under the BOUND home, where pathlib's own expanduser --
             which reads $HOME, then the passwd entry -- lands elsewhere
        """
        facts = ambient.AmbientFacts(
            home=Path("/tmp/home-one"), cwd=Path("/tmp/cwd-one"), env={"WHICH": "one"}
        )
        with patch.dict(os.environ, {"HOME": "/from/env"}, clear=False):
            with ambient.active(facts):
                self.assertEqual(expanduser("~/x"), Path("/tmp/home-one/x"))
                self.assertEqual(Path("~/x").expanduser(), Path("/from/env/x"))


if __name__ == "__main__":
    unittest.main()
