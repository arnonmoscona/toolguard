"""
Unit tests for toolguard.ambient: where toolguard reads home, cwd and the
environment.

Resolution happens when something asks, never at import. A binding lasts exactly
one ``with`` block, so two invocations sharing a process cannot inherit each
other's machine state. resolve() tolerates a machine with no home, because an
entry point calls it.
"""

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import ambient
from toolguard.path_utils import iter_dirs_upward

_AMBIENT_SOURCE = Path(ambient.__file__)

#: Names that must not be referenced by a module-scope statement in ambient.py.
_AMBIENT_READS = ("home", "cwd", "getcwd", "environ", "getenv", "expanduser")


def _module_level_names(source_path):
    """
    Names referenced at module scope in *source_path*. A module-level ``def`` or
    ``class`` is skipped whole, so its decorators and parameter defaults go
    uninspected though they run at import.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Attribute):
                names.append(descendant.attr)
            elif isinstance(descendant, ast.Name):
                names.append(descendant.id)
    return names


class TestResolutionIsLazy(unittest.TestCase):
    """Nothing is read at import; with nothing bound, each value comes from the call."""

    def test_no_ambient_state_is_read_at_module_scope(self):
        """
        Given ambient.py, whose whole purpose is to be the mockable door
        When its module-scope statements are parsed
        Then none of them reads the home directory, the current directory or the
             environment -- a value captured at import predates every test's
             patch and silently ignores it
        """
        read_at_import = sorted(
            set(_module_level_names(_AMBIENT_SOURCE)) & set(_AMBIENT_READS)
        )
        self.assertEqual(
            read_at_import,
            [],
            f"ambient.py reads {read_at_import} at import, so a later patch "
            f"cannot be seen",
        )

    def test_resolve_reads_the_machine_at_the_moment_it_is_called(self):
        """
        Given a patched Path.home installed after this module was imported
        When resolve() is called
        Then it reports the patched home, not one captured earlier
        """
        fake_home = Path("/tmp/some-fake-home")
        with patch.object(Path, "home", return_value=fake_home):
            self.assertEqual(ambient.resolve().home, fake_home)

    def test_home_observes_a_patched_path_home_when_nothing_is_bound(self):
        """
        Given no active binding
        When home() is called under a patched Path.home
        Then it returns the patched value
        """
        fake_home = Path("/tmp/another-fake-home")
        with patch.object(Path, "home", return_value=fake_home):
            self.assertEqual(ambient.home(), fake_home)

    def test_env_var_reads_the_live_environment_when_nothing_is_bound(self):
        """
        Given no active binding
        When env_var() is called inside a patch.dict of the environment
        Then it reports the patched value
        """
        with patch.dict(os.environ, {"TOOLGUARD_TEST_MARKER": "live"}, clear=False):
            self.assertEqual(ambient.env_var("TOOLGUARD_TEST_MARKER"), "live")

    def test_env_var_returns_the_default_for_an_unset_name(self):
        """
        Given a variable that is not set
        When env_var() is called with a default
        Then the default comes back
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                ambient.env_var("TOOLGUARD_TEST_MARKER", "fallback"), "fallback"
            )


class TestResolveNeverRaisesAtAnEntryPoint(unittest.TestCase):
    """resolve() is called at an entry point, so it must not raise there."""

    def test_resolve_records_none_rather_than_raising(self):
        """
        Given a machine where the home directory cannot be resolved
        When resolve() is called
        Then it returns facts with home None instead of raising into the entry
             point, which still has a decision to emit
        """
        with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
            self.assertIsNone(ambient.resolve().home)

    def test_resolve_records_an_unresolvable_cwd_as_none(self):
        """
        Given a process whose current directory cannot be resolved (a deleted cwd)
        When resolve() is called
        Then cwd comes back None rather than the call raising
        """
        with patch.object(Path, "cwd", side_effect=OSError("no cwd")):
            self.assertIsNone(ambient.resolve().cwd)

    def test_home_still_raises_for_a_caller_that_needs_the_value(self):
        """
        Given facts bound with an unresolved home
        When home() is called
        Then the live lookup runs and raises, so a caller's own handling of a
             homeless machine is reached exactly as it was before the binding
        """
        facts = ambient.AmbientFacts(home=None, cwd=Path("/tmp"), env={})
        with ambient.active(facts):
            with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
                with self.assertRaises(RuntimeError):
                    ambient.home()


class TestABindingLastsExactlyOneBlock(unittest.TestCase):
    """The invocation scope, and the leak it exists to prevent."""

    def setUp(self):
        self.first = ambient.AmbientFacts(
            home=Path("/tmp/home-one"), cwd=Path("/tmp/cwd-one"), env={"WHICH": "one"}
        )
        self.second = ambient.AmbientFacts(
            home=Path("/tmp/home-two"), cwd=Path("/tmp/cwd-two"), env={"WHICH": "two"}
        )

    def test_bound_facts_are_what_the_accessors_report(self):
        """
        Given facts bound for the block
        When home(), cwd() and env_var() are called inside it
        Then all three report the bound values
        """
        with ambient.active(self.first):
            self.assertEqual(ambient.home(), Path("/tmp/home-one"))
            self.assertEqual(ambient.cwd(), Path("/tmp/cwd-one"))
            self.assertEqual(ambient.env_var("WHICH"), "one")

    def test_a_bound_home_governs_tilde_expansion(self):
        """
        Given facts bound for the block, and a process $HOME pointing elsewhere
        When a '~' path is expanded through ambient
        Then it lands under the BOUND home, where pathlib's own expanduser --
             which reads $HOME, then the passwd entry -- lands elsewhere
        """
        with patch.dict(os.environ, {"HOME": "/from/env"}, clear=False):
            with ambient.active(self.first):
                self.assertEqual(ambient.expanduser("~/x"), Path("/tmp/home-one/x"))
                self.assertEqual(Path("~/x").expanduser(), Path("/from/env/x"))

    def test_env_reports_the_bound_snapshot(self):
        """
        Given facts bound for the block
        When env() is called inside it
        Then the bound snapshot comes back, not the live process environment
        """
        with ambient.active(self.first):
            self.assertEqual(dict(ambient.env()), {"WHICH": "one"})

    def test_two_invocations_in_one_process_do_not_share_state(self):
        """
        Given two sequential bindings in the same process
        When each block reads the accessors
        Then each sees only its own facts -- the first invocation's machine
             state never reaches the second
        """
        with ambient.active(self.first):
            first_seen = ambient.home()
        with ambient.active(self.second):
            second_seen = ambient.home()

        self.assertEqual(first_seen, Path("/tmp/home-one"))
        self.assertEqual(second_seen, Path("/tmp/home-two"))

    def test_leaving_a_block_restores_the_live_reading(self):
        """
        Given a binding that has been left
        When home() is called afterwards
        Then it reads the machine again rather than the departed block's value
        """
        with ambient.active(self.first):
            pass

        fake_home = Path("/tmp/back-to-live")
        with patch.object(Path, "home", return_value=fake_home):
            self.assertEqual(ambient.home(), fake_home)

    def test_an_exception_inside_the_block_still_releases_the_binding(self):
        """
        Given a block that raises, as a crashing invocation does
        When the exception propagates out of active()
        Then the binding is released, so the next invocation is not governed by
             the crashed one's machine state
        """
        with self.assertRaises(ValueError):
            with ambient.active(self.first):
                raise ValueError("boom")

        self.assertIsNone(ambient._active)

    def test_a_nested_binding_restores_the_outer_one(self):
        """
        Given a binding entered inside another
        When the inner block is left
        Then the outer block's facts govern again
        """
        with ambient.active(self.first):
            with ambient.active(self.second):
                self.assertEqual(ambient.home(), Path("/tmp/home-two"))
            self.assertEqual(ambient.home(), Path("/tmp/home-one"))


class TestDerivedAccessorsAnswerFromTheFactTheyReadFrom(unittest.TestCase):
    """
    env_var answers from env(), and expanduser from home() for a leading bare
    '~', so overriding a fact governs the accessors derived from it. A second
    read point would be a seam a test patches and silently never reaches.
    """

    def test_env_var_observes_a_patched_env(self):
        """
        Given ambient.env patched and nothing else
        When env_var() asks for a name the patched environment holds
        Then it reports the patched value, so a test isolating the environment
             through env() is not bypassed
        """
        with patch("toolguard.ambient.env", return_value={"K": "patched"}):
            self.assertEqual(ambient.env_var("K"), "patched")

    def test_a_patched_env_governs_absence_too(self):
        """
        Given ambient.env patched to an environment lacking a name that the
              process environment does set
        When env_var() is called with a default
        Then the default comes back -- the override is authoritative, with no
             second read of the process environment behind it
        """
        with patch.dict(os.environ, {"TOOLGUARD_TEST_MARKER": "live"}, clear=False):
            with patch("toolguard.ambient.env", return_value={}):
                self.assertEqual(
                    ambient.env_var("TOOLGUARD_TEST_MARKER", "fallback"), "fallback"
                )

    def test_expanduser_resolves_a_tilde_through_the_home_accessor(self):
        """
        Given ambient.home patched and nothing else
        When expanduser() expands a path written with a leading '~'
        Then it lands under the patched home, so a '~' in configuration cannot
             route around a test that redirected home
        """
        with patch("toolguard.ambient.home", return_value=Path("/patched/home")):
            self.assertEqual(
                ambient.expanduser("~/.toolguard"), Path("/patched/home/.toolguard")
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
                    self.assertEqual(ambient.expanduser(raw), expected)


class TestPatchingAmbientHomeRedirectsPathUtils(unittest.TestCase):
    """
    Patching ambient.home alone is enough to redirect a consumer, without
    reaching into pathlib.
    """

    def test_the_upward_walk_stops_at_the_patched_ambient_home(self):
        """
        Given a home directory supplied by patching ambient.home and nothing else
        When path_utils walks upward from a directory beneath it
        Then the walk stops at that home
        """
        fake_home = Path("/tmp/one-door-home")
        start = fake_home / "projects" / "thing"
        with patch("toolguard.ambient.home", return_value=fake_home):
            walked = list(iter_dirs_upward(start))

        self.assertEqual(walked[-1], fake_home)


if __name__ == "__main__":
    unittest.main()
