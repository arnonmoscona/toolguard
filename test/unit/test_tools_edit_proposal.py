"""Unit tests for the general edit-proposal model and in-memory application."""

import unittest
from pathlib import Path
from types import MappingProxyType

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.config_access import (
    per_layer_rules,
    with_layer_allow_replaced,
    with_layer_rules_replaced,
)
from toolguard.tools.edit_proposal import (
    ACTION_MOVE,
    ACTION_REPLACE,
    EditProposal,
    RuleEdit,
    apply_edits,
    edit_proposal_from_dict,
    edit_proposal_to_dict,
)


def _prov(level: str = "project", specificity: int = 0) -> Provenance:
    """Build a Provenance at the given hierarchy level/specificity."""
    return Provenance(
        level=level,
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(f"/{level}/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _config(*layers: ConfigLayer) -> Configuration:
    """Wrap layers into a Configuration."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _layer(prov: Provenance, allow=(), deny=(), ask=()) -> ConfigLayer:
    """Build a single-tool (Bash) config layer with the given lists."""
    return ConfigLayer(
        provenance=prov,
        content=MappingProxyType(
            {
                "permissions": {
                    "allow": [f"Bash({p})" for p in allow],
                    "deny": [f"Bash({p})" for p in deny],
                    "ask": [f"Bash({p})" for p in ask],
                }
            }
        ),
    )


class TestWithLayerRulesReplaced(unittest.TestCase):
    """The section-generic synthetic-config primitive."""

    def test_edits_the_deny_section(self):
        """
        Given a layer with a deny list
        When with_layer_rules_replaced adds a pattern to 'deny'
        Then the deny list gains the wrapped pattern and allow is untouched.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"], deny=["rm -rf:*"]))
        result = with_layer_rules_replaced(
            config, "Bash", prov, "deny", set(), ["git push:*"]
        )
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.deny, ("rm -rf:*", "git push:*"))
        self.assertEqual(lr.allow, ("git:*",))

    def test_edits_the_ask_section(self):
        """
        Given a layer with an ask list
        When with_layer_rules_replaced removes an ask pattern
        Then that pattern is gone from ask.
        """
        prov = _prov()
        config = _config(_layer(prov, ask=["curl:*", "wget:*"]))
        result = with_layer_rules_replaced(
            config, "Bash", prov, "ask", {"curl:*"}, []
        )
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.ask, ("wget:*",))

    def test_unknown_list_type_raises(self):
        """
        Given an invalid list_type
        When with_layer_rules_replaced is called
        Then it raises ValueError.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        with self.assertRaises(ValueError):
            with_layer_rules_replaced(config, "Bash", prov, "bogus", set(), [])

    def test_unmatched_provenance_returns_config_unchanged(self):
        """
        Given a provenance matching no layer
        When with_layer_rules_replaced is called
        Then the original config is returned unchanged (safe fall-through).
        """
        prov = _prov()
        other = _prov(level="user", specificity=1)
        config = _config(_layer(prov, allow=["git:*"]))
        result = with_layer_rules_replaced(
            config, "Bash", other, "allow", set(), ["ls:*"]
        )
        self.assertIs(result, config)

    def test_allow_wrapper_still_delegates(self):
        """
        Given the retained allow-only wrapper
        When with_layer_allow_replaced is used
        Then it edits the allow list exactly as before (single implementation).
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        result = with_layer_allow_replaced(config, "Bash", prov, {"git:*"}, ["git status:*"])
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.allow, ("git status:*",))


class TestApplyEdits(unittest.TestCase):
    """apply_edits enacts multi-section, multi-layer proposals in memory."""

    def test_replace_spanning_two_sections(self):
        """
        Given a REPLACE proposal that narrows an allow AND adds a deny
        When apply_edits enacts it
        Then the allow is narrowed and the deny gains the guard (both sections).
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="tighten git",
            edits=(
                RuleEdit("Bash", "allow", prov, ("git:*",), ("git status:*",)),
                RuleEdit("Bash", "deny", prov, (), ("git push:*",)),
            ),
        )
        result = apply_edits(config, [proposal])
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.allow, ("git status:*",))
        self.assertEqual(lr.deny, ("git push:*",))

    def test_move_across_layers(self):
        """
        Given a MOVE proposal removing a rule from the project layer and adding
            it to the user layer
        When apply_edits enacts it
        Then the rule leaves the project allow and appears in the user allow.
        """
        proj = _prov(specificity=0)
        user = _prov(level="user", specificity=1)
        config = _config(
            _layer(proj, allow=["ls:*"]),
            _layer(user, allow=[]),
        )
        proposal = EditProposal(
            action=ACTION_MOVE,
            tool="Bash",
            rationale="promote ls",
            edits=(
                RuleEdit("Bash", "allow", proj, ("ls:*",), ()),
                RuleEdit("Bash", "allow", user, (), ("ls:*",)),
            ),
        )
        result = apply_edits(config, [proposal])
        layers = per_layer_rules(result, "Bash")
        by_level = {lr.provenance.level: lr for lr in layers}
        self.assertEqual(by_level["project"].allow, ())
        self.assertEqual(by_level["user"].allow, ("ls:*",))

    def test_stale_edit_is_skipped(self):
        """
        Given an edit whose provenance matches no layer
        When apply_edits runs
        Then it is silently skipped and the config is otherwise unchanged.
        """
        prov = _prov()
        ghost = _prov(level="enterprise", specificity=9)
        config = _config(_layer(prov, allow=["git:*"]))
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="stale",
            edits=(RuleEdit("Bash", "allow", ghost, (), ("nope:*",)),),
        )
        result = apply_edits(config, [proposal])
        self.assertEqual(per_layer_rules(result, "Bash")[0].allow, ("git:*",))


class TestEditProposalSerialization(unittest.TestCase):
    """The JSON contract shared with toolguard-audit --edits and audit output."""

    def test_round_trips_exactly(self):
        """
        Given an EditProposal spanning two sections with a full provenance
        When it is serialized and reconstructed
        Then the reconstructed proposal equals the original (provenance exact).
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="tighten",
            edits=(
                RuleEdit("Bash", "allow", prov, ("git:*",), ("git status:*",)),
                RuleEdit("Bash", "deny", prov, (), ("git push:*",)),
            ),
            origin="audit:arbitrary-exec-allow",
        )
        restored = edit_proposal_from_dict(edit_proposal_to_dict(proposal))
        self.assertEqual(restored, proposal)


if __name__ == "__main__":
    unittest.main()
