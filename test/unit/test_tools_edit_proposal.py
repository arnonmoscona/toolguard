"""Unit tests for the general edit-proposal model and in-memory application."""

import json
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
    ACTION_NARROW,
    ACTION_REMOVE,
    ACTION_REPLACE,
    EditProposal,
    RuleEdit,
    apply_edits,
    edit_proposal_from_dict,
    edit_proposal_to_dict,
    rule_edit_from_dict,
    validate_edit_proposal,
)

#: Every layer edit is matched by whole-``Provenance`` equality, so a fixture whose
#: fields all hold their real-world default value cannot tell a field that is carried
#: from a field that is hardcoded. These defaults are deliberately off-default.
_DEFAULT_SPECIFICITY = 2
_START_DIR = Path("/no/such/project")


def _prov(
    level: str = "project",
    specificity: int = _DEFAULT_SPECIFICITY,
    source_type: str = "toolguard_hook",
    file_format: str = "toml",
    path: str = "",
) -> Provenance:
    """Build a Provenance at the given hierarchy level/specificity."""
    return Provenance(
        level=level,
        source_type=source_type,
        file_format=file_format,
        path=Path(path or f"/{level}/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _config(*layers: ConfigLayer, **kwargs) -> Configuration:
    """Wrap layers into a Configuration with a non-None start_dir."""
    kwargs.setdefault("start_dir", _START_DIR)
    return Configuration(layers=tuple(layers), **kwargs)


def _layer(prov: Provenance, allow=(), deny=(), ask=(), extra=None) -> ConfigLayer:
    """Build a single-tool (Bash) config layer with the given lists."""
    content = {
        "permissions": {
            "allow": [f"Bash({p})" for p in allow],
            "deny": [f"Bash({p})" for p in deny],
            "ask": [f"Bash({p})" for p in ask],
        }
    }
    if extra:
        content.update(extra)
    return ConfigLayer(provenance=prov, content=MappingProxyType(content))


def _raw(config: Configuration, index: int = 0, list_type: str = "allow"):
    """
    Return a layer's RAW permission list, bypassing :func:`per_layer_rules`.

    ``per_layer_rules`` keys its lookup by ``Provenance``, so two layers with equal
    provenance collapse into one entry -- it cannot be used to observe them apart.
    """
    return config.layers[index].content["permissions"][list_type]


class TestWithLayerRulesReplaced(unittest.TestCase):
    """The section-generic synthetic-config primitive."""

    def test_edits_the_deny_section(self):
        """
        Given a layer with a deny list
        When with_layer_rules_replaced adds a pattern to 'deny'
        Then the deny list gains the wrapped pattern at the END and allow is untouched.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"], deny=["rm -rf:*"]))
        result = with_layer_rules_replaced(
            config, "Bash", prov, "deny", set(), ["git push:*"]
        )
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.deny, ("rm -rf:*", "git push:*"))
        self.assertEqual(lr.allow, ("git:*",))
        self.assertEqual(
            _raw(result, list_type="deny"), ["Bash(rm -rf:*)", "Bash(git push:*)"]
        )

    def test_edits_the_ask_section(self):
        """
        Given a layer with an ask list
        When with_layer_rules_replaced removes an ask pattern
        Then that pattern is gone from ask and the other one survives.
        """
        prov = _prov()
        config = _config(_layer(prov, ask=["curl:*", "wget:*"]))
        result = with_layer_rules_replaced(config, "Bash", prov, "ask", {"curl:*"}, [])
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.ask, ("wget:*",))

    def test_unknown_list_type_raises(self):
        """
        Given an invalid list_type
        When with_layer_rules_replaced is called
        Then it raises ValueError naming the rejected value.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        with self.assertRaisesRegex(ValueError, "bogus"):
            with_layer_rules_replaced(config, "Bash", prov, "bogus", set(), [])

    def test_unmatched_provenance_returns_config_unchanged(self):
        """
        Given a provenance matching no layer
        When with_layer_rules_replaced is called
        Then the original config object is returned (safe fall-through).
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
        Given the allow-only wrapper
        When with_layer_allow_replaced is used
        Then the allow list has the removed pattern gone and the added one in place,
            and neither deny nor ask is touched.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"], deny=["rm:*"], ask=["curl:*"]))
        result = with_layer_allow_replaced(
            config, "Bash", prov, {"git:*"}, ["git status:*"]
        )
        lr = per_layer_rules(result, "Bash")[0]
        self.assertEqual(lr.allow, ("git status:*",))
        self.assertEqual(lr.deny, ("rm:*",))
        self.assertEqual(lr.ask, ("curl:*",))

    def test_removing_plain_pattern_preserves_untouched_structured_entry(self):
        """
        Given an allow list holding a plain pattern and an untouched structured entry
        When with_layer_rules_replaced removes only the plain pattern
        Then it does not raise, the plain pattern is gone, and the structured entry
            survives as the IDENTICAL dict object (not rebuilt).
        """
        prov = _prov()
        structured = {"match": "Bash(git push:*)", "additionalContext": "careful"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(config, "Bash", prov, "allow", {"git:*"}, [])

        raw_allow = _raw(result)
        self.assertEqual(len(raw_allow), 1)
        self.assertIs(raw_allow[0], structured)

    def test_removing_structured_entry_by_pattern(self):
        """
        Given an allow list with a plain pattern and a structured entry
        When with_layer_rules_replaced removes the structured entry's pattern body
        Then the structured entry is gone and the plain pattern is untouched.
        """
        prov = _prov()
        structured = {"match": "Bash(git push:*)", "additionalContext": "careful"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", {"git push:*"}, []
        )

        self.assertEqual(_raw(result), ["Bash(git:*)"])

    def test_adding_pattern_to_list_with_structured_entry(self):
        """
        Given an allow list containing only a structured entry
        When with_layer_rules_replaced adds a new plain pattern
        Then the new pattern is appended at the end and the structured entry is
            unchanged and still first.
        """
        prov = _prov()
        structured = {"match": "Bash(git push:*)", "additionalContext": "careful"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": [structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        raw_allow = _raw(result)
        self.assertEqual(len(raw_allow), 2)
        self.assertIs(raw_allow[0], structured)
        self.assertEqual(raw_allow[1], "Bash(ls:*)")

    def test_malformed_entry_is_preserved_not_dropped(self):
        """
        Given an allow list holding a malformed structured entry (no 'match' key)
        When with_layer_rules_replaced removes an unrelated pattern
        Then the malformed entry is preserved as-is, not silently dropped.
        """
        prov = _prov()
        malformed = {"additionalContext": "orphaned, no match key"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", malformed],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(config, "Bash", prov, "allow", {"git:*"}, [])

        raw_allow = _raw(result)
        self.assertEqual(len(raw_allow), 1)
        self.assertIs(raw_allow[0], malformed)

    def test_layer_metadata_survives_rebuild(self):
        """
        Given a layer with unexpected_keys, duplicate_format, and shadowed_path set
        When with_layer_rules_replaced modifies that layer's list
        Then the rebuilt layer still carries those same field values.
        """
        prov = _prov()
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {"permissions": {"allow": ["Bash(git:*)"], "deny": [], "ask": []}}
            ),
            unexpected_keys=("stray_key",),
            duplicate_format=True,
            shadowed_path=Path("/other/.claude/toolguard_hook.toml"),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        rebuilt = result.layers[0]
        self.assertEqual(rebuilt.unexpected_keys, ("stray_key",))
        self.assertTrue(rebuilt.duplicate_format)
        self.assertEqual(
            rebuilt.shadowed_path, Path("/other/.claude/toolguard_hook.toml")
        )

    def test_start_dir_survives_the_rebuild(self):
        """
        Given a configuration whose start_dir is set
        When with_layer_rules_replaced rebuilds it
        Then the returned Configuration carries the same start_dir.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )
        self.assertIsNot(result, config)
        self.assertEqual(result.start_dir, _START_DIR)

    def test_sections_outside_permissions_survive_the_rebuild(self):
        """
        Given a layer that also declares hard_deny and takeover_mode
        When with_layer_rules_replaced edits only its allow list
        Then both other sections still resolve through the Configuration's own
            accessors -- an edit must not drop a hard deny.
        """
        prov = _prov()
        layer = _layer(
            prov,
            allow=["git:*"],
            extra={
                "hard_deny": {"deny": ["Bash(rm -rf /:*)"]},
                "takeover_mode": {"enabled": True},
            },
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        self.assertEqual(result.hard_deny("Bash"), config.hard_deny("Bash"))
        self.assertEqual(result.hard_deny("Bash")[0], ("rm -rf /:*",))
        self.assertTrue(result.takeover_mode().enabled)

    def test_parse_failures_survive_the_rebuild(self):
        """
        Given a configuration carrying a parse_failures entry, which clamps every
            governed decision to 'ask' and is reported as an 'error' issue
        When with_layer_rules_replaced rebuilds it
        Then the rebuilt Configuration still carries that parse failure.

        RED at the time of writing: the rebuild calls
        ``Configuration(layers=..., start_dir=...)`` and never passes
        ``parse_failures``, so the field silently resets to ``()`` and the error
        issue vanishes from the synthetic config an as-if-enacted audit reads.
        """
        prov = _prov()
        broken = (Path("/broken.toml"), "boom")
        config = _config(_layer(prov, allow=["git:*"]), parse_failures=(broken,))

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        self.assertEqual(result.parse_failures, (broken,))
        self.assertIn("error", [issue.level for issue in result.validation_issues()])

    def test_only_the_first_layer_with_an_equal_provenance_is_edited(self):
        """
        Given two layers whose Provenance objects are equal
        When with_layer_rules_replaced edits that provenance
        Then only the FIRST layer's list changes and the second is untouched.

        Read from raw layer content: per_layer_rules keys by Provenance and would
        collapse the two layers into one entry.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["a:*"]), _layer(prov, allow=["b:*"]))

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["z:*"]
        )

        self.assertEqual(_raw(result, 0), ["Bash(a:*)", "Bash(z:*)"])
        self.assertEqual(_raw(result, 1), ["Bash(b:*)"])

    def test_a_non_table_permissions_section_returns_the_config_unchanged(self):
        """
        Given a layer whose [permissions] is a scalar rather than a table
        When with_layer_rules_replaced targets it
        Then the original config object is returned and nothing is rebuilt.
        """
        prov = _prov()
        layer = ConfigLayer(
            provenance=prov, content=MappingProxyType({"permissions": "hello"})
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        self.assertIs(result, config)

    def test_a_non_list_section_returns_the_config_unchanged(self):
        """
        Given a layer whose allow value is a bare string rather than a list
        When with_layer_rules_replaced targets allow
        Then the original config object is returned and nothing is rebuilt.
        """
        prov = _prov()
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType({"permissions": {"allow": "Bash(git:*)"}}),
        )
        config = _config(layer)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", set(), ["ls:*"]
        )

        self.assertIs(result, config)

    def test_a_native_layer_pattern_is_removed_by_body(self):
        """
        Given a NATIVE (Claude settings) layer holding an allow pattern
        When with_layer_rules_replaced removes that pattern's body
        Then the pattern is gone -- native normalization is applied to the layer
            being edited, not the one the caller happens to have in hand.
        """
        prov = _prov(
            level="user",
            specificity=1,
            source_type="claude",
            file_format="json",
            path="/user/.claude/settings.json",
        )
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {"permissions": {"allow": ["Bash(git:*)"], "deny": [], "ask": []}}
            ),
        )
        config = _config(layer)
        self.assertTrue(layer.is_native)

        result = with_layer_rules_replaced(
            config, "Bash", prov, "allow", {"git:*"}, ["git status:*"]
        )

        self.assertEqual(_raw(result), ["Bash(git status:*)"])

    def test_an_already_wrapped_added_pattern_raises(self):
        """
        Given an added pattern that already carries its Tool(...) wrapper
        When with_layer_rules_replaced appends it
        Then it raises ValueError instead of silently double-wrapping.

        added_patterns are contracted to be wrapper-free, and
        `edit_proposal_from_dict` builds these straight from hand-written JSON -- a
        hand-authored --edits file that includes the wrapper must fail loud rather
        than silently yield Bash(Bash(git:*)), which matches nothing and reports no
        error.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=[]))

        with self.assertRaisesRegex(ValueError, "already wrapped"):
            with_layer_rules_replaced(
                config, "Bash", prov, "allow", set(), ["Bash(git:*)"]
            )


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
        Then the ORIGINAL config object comes back, unchanged and unrebuilt.
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
        self.assertIs(result, config)
        self.assertEqual(per_layer_rules(result, "Bash")[0].allow, ("git:*",))

    def test_the_edits_tool_decides_not_the_proposals_headline_tool(self):
        """
        Given a proposal whose headline tool is Bash but whose only edit names Read
        When apply_edits enacts it
        Then the Read rule is the one removed and the Bash rule is untouched.
        """
        prov = _prov()
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", "Read(/etc/**)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)
        proposal = EditProposal(
            action=ACTION_REMOVE,
            tool="Bash",
            rationale="headline says Bash",
            edits=(RuleEdit("Read", "allow", prov, ("/etc/**",), ()),),
        )

        result = apply_edits(config, [proposal])

        self.assertEqual(_raw(result), ["Bash(git:*)"])

    def test_the_description_can_contradict_the_edits_and_nothing_objects(self):
        """
        Given two proposals sharing one identical edit tuple but disagreeing on
            action, tool and rationale
        When apply_edits enacts each
        Then both produce the identical configuration.

        Characterization of an unguarded surface, not desired behaviour: action, tool
        and rationale are the description a consumer renders, the edits are what is
        enacted, and nothing checks that they agree -- so a proposal captioned
        'narrow Bash' can enact a Read-list broadening.
        """
        prov = _prov()
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git:*)", "Read(/etc/**)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _config(layer)
        edits = (RuleEdit("Read", "allow", prov, (), ("/**",)),)
        narrowing_caption = EditProposal(
            action=ACTION_NARROW, tool="Bash", rationale="tighten Bash", edits=edits
        )
        removal_caption = EditProposal(
            action=ACTION_REMOVE,
            tool="Write",
            rationale="delete a Write rule",
            edits=edits,
        )

        under_a = _raw(apply_edits(config, [narrowing_caption]))
        under_b = _raw(apply_edits(config, [removal_caption]))

        self.assertEqual(under_a, ["Bash(git:*)", "Read(/etc/**)", "Read(/**)"])
        self.assertEqual(under_a, under_b)

    def test_edits_within_a_proposal_apply_in_order(self):
        """
        Given one proposal holding an add of 'git:*' followed by a remove of 'git:*'
        When apply_edits enacts it
        Then the allow list ends EMPTY -- the later edit sees the earlier one's result.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=[]))
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="add then take back",
            edits=(
                RuleEdit("Bash", "allow", prov, (), ("git:*",)),
                RuleEdit("Bash", "allow", prov, ("git:*",), ()),
            ),
        )

        self.assertEqual(_raw(apply_edits(config, [proposal])), [])

        reversed_proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="take back then add",
            edits=tuple(reversed(proposal.edits)),
        )
        self.assertEqual(
            _raw(apply_edits(config, [reversed_proposal])), ["Bash(git:*)"]
        )

    def test_proposals_apply_in_list_order(self):
        """
        Given two proposals touching one allow list, one adding 'git:*' and one
            removing it
        When apply_edits enacts them in each order
        Then the results differ -- list order is load-bearing, not incidental.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        adding = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="re-add",
            edits=(RuleEdit("Bash", "allow", prov, (), ("git:*",)),),
        )
        removing = EditProposal(
            action=ACTION_REMOVE,
            tool="Bash",
            rationale="drop",
            edits=(RuleEdit("Bash", "allow", prov, ("git:*",), ()),),
        )

        self.assertEqual(_raw(apply_edits(config, [adding, removing])), [])
        self.assertEqual(_raw(apply_edits(config, [removing, adding])), ["Bash(git:*)"])

    def test_a_proposal_that_enacts_nothing_returns_the_original_object(self):
        """
        Given an empty proposal list, a proposal with no edits, and a proposal whose
            every edit is stale
        When apply_edits runs each
        Then the ORIGINAL config object comes back in all three cases -- object
            identity is the only signal that nothing was enacted.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git:*"]))
        empty_proposal = EditProposal(
            action=ACTION_REPLACE, tool="Bash", rationale="nothing", edits=()
        )
        stale_proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="stale",
            edits=(
                RuleEdit(
                    "Bash",
                    "allow",
                    _prov(level="enterprise", specificity=9),
                    (),
                    ("x:*",),
                ),
            ),
        )

        self.assertIs(apply_edits(config, []), config)
        self.assertIs(apply_edits(config, [empty_proposal]), config)
        self.assertIs(apply_edits(config, [stale_proposal]), config)

    def test_a_removal_that_misses_still_applies_the_addition(self):
        """
        Given a REPLACE proposal narrowing 'git *' to 'git status:*' against a layer
            that no longer holds 'git *' under that spelling
        When apply_edits enacts it
        Then the layer ends up with BOTH the untouched broad rule and the new narrow
            one, and a fresh Configuration object comes back as though it had worked.

        Characterization of a known defect, not desired behaviour: half a narrowing
        proposal is a broadening, and neither the returned Configuration nor its
        object identity distinguishes a fully enacted proposal from this one.
        """
        prov = _prov()
        config = _config(_layer(prov, allow=["git *"]))
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Bash",
            rationale="narrow git",
            edits=(RuleEdit("Bash", "allow", prov, ("gone *",), ("git status:*",)),),
        )

        result = apply_edits(config, [proposal])

        self.assertIsNot(result, config)
        self.assertEqual(_raw(result), ["Bash(git *)", "Bash(git status:*)"])


class TestValidateEditProposal(unittest.TestCase):
    """
    validate_edit_proposal is a separate, opt-in caption-vs-edits check -- it is
    NOT called by apply_edits (see TestApplyEdits.
    test_the_description_can_contradict_the_edits_and_nothing_objects, which pins
    apply_edits' own no-judgement behaviour unchanged).
    """

    def test_a_tool_matching_one_of_several_edited_tools_passes(self):
        """
        Given a proposal whose headline tool is the SECOND of two edits' tools
        When validate_edit_proposal checks it
        Then it does not raise -- tool is membership, not "matches the first edit".
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Write",
            rationale="two sections",
            edits=(
                RuleEdit("Bash", "allow", prov, (), ("git status:*",)),
                RuleEdit("Write", "deny", prov, (), ("/etc/**",)),
            ),
        )
        validate_edit_proposal(proposal)  # must not raise

    def test_a_tool_naming_none_of_the_edited_tools_raises(self):
        """
        Given a proposal captioned Bash whose only edit touches Read
        When validate_edit_proposal checks it
        Then it raises ValueError naming the mismatched tool.
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_NARROW,
            tool="Bash",
            rationale="tighten Bash",
            edits=(RuleEdit("Read", "allow", prov, (), ("/**",)),),
        )
        with self.assertRaisesRegex(ValueError, "'Bash'"):
            validate_edit_proposal(proposal)

    def test_an_empty_edits_proposal_never_raises_on_tool(self):
        """
        Given a proposal whose edits tuple is empty
        When validate_edit_proposal checks it
        Then it does not raise -- there is nothing for the headline tool to
            disagree with.
        """
        proposal = EditProposal(
            action=ACTION_REPLACE, tool="Bash", rationale="nothing yet", edits=()
        )
        validate_edit_proposal(proposal)  # must not raise

    def test_a_remove_carrying_added_patterns_raises(self):
        """
        Given a 'remove' proposal whose one edit carries added_patterns
        When validate_edit_proposal checks it
        Then it raises ValueError -- a removal that adds is incoherent on its face.
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_REMOVE,
            tool="Read",
            rationale="delete a Read rule",
            edits=(RuleEdit("Read", "allow", prov, (), ("/**",)),),
        )
        with self.assertRaisesRegex(ValueError, "added_patterns"):
            validate_edit_proposal(proposal)

    def test_a_remove_with_only_removed_patterns_passes(self):
        """
        Given a 'remove' proposal whose edit carries only removed_patterns
        When validate_edit_proposal checks it
        Then it does not raise.
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_REMOVE,
            tool="Read",
            rationale="delete a Read rule",
            edits=(RuleEdit("Read", "allow", prov, ("/etc/**",), ()),),
        )
        validate_edit_proposal(proposal)  # must not raise

    def test_an_unrecognized_action_with_coherent_tool_and_edits_passes(self):
        """
        Given a proposal whose action is not one of ACTIONS but whose tool and
            edits agree
        When validate_edit_proposal checks it
        Then it does not raise -- action coherence is only enforced for the
            recognized 'remove' label, per the module's advisory-action contract.
        """
        prov = _prov()
        proposal = EditProposal(
            action="obliterate",
            tool="Write",
            rationale="not a known action",
            edits=(RuleEdit("Write", "deny", prov, (), ("/**",)),),
        )
        validate_edit_proposal(proposal)  # must not raise

    def test_rationale_is_never_checked(self):
        """
        Given a proposal whose rationale text names a tool nothing in the edits
            touches
        When validate_edit_proposal checks it
        Then it does not raise -- rationale is free prose, deliberately unchecked.
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_NARROW,
            tool="Write",
            rationale="this is actually about Bash, not Write at all",
            edits=(RuleEdit("Write", "allow", prov, (), ("/**",)),),
        )
        validate_edit_proposal(proposal)  # must not raise

    def test_verification_is_never_checked(self):
        """
        Given a coherent proposal carrying a verification value with no
            counterpart in edits
        When validate_edit_proposal checks it
        Then it does not raise -- verification is producer-derived, not
            something edits can confirm or contradict.
        """
        prov = _prov()
        proposal = EditProposal(
            action=ACTION_REPLACE,
            tool="Write",
            rationale="consolidated",
            edits=(RuleEdit("Write", "allow", prov, ("/a/**",), ("/**",)),),
            verification="unverified",
        )
        validate_edit_proposal(proposal)  # must not raise


class TestEditProposalSerialization(unittest.TestCase):
    """The JSON contract shared with toolguard-audit --edits and audit output."""

    @staticmethod
    def _distinctive_proposal() -> EditProposal:
        """
        A proposal in which no field holds its type's default or the fixture-common
        value, so a serializer that hardcodes any one of them is visible.
        """
        user = _prov(
            level="user",
            specificity=7,
            source_type="claude",
            file_format="json",
            path="/u/.claude/settings.json",
        )
        enterprise = _prov(level="enterprise", specificity=11)
        return EditProposal(
            action=ACTION_NARROW,
            tool="Read",
            rationale="tighten",
            edits=(
                RuleEdit("Read", "ask", user, ("/a/**",), ("/b/**",)),
                RuleEdit("Write", "deny", enterprise, (), ("/etc/**",)),
            ),
            origin="audit:arbitrary-exec-allow",
        )

    def test_round_trips_exactly(self):
        """
        Given a proposal whose two edits differ in tool, list_type and provenance,
            and whose action/tool/provenance fields all hold off-default values
        When it is serialized and reconstructed
        Then the reconstructed proposal equals the original, field for field.
        """
        proposal = self._distinctive_proposal()
        restored = edit_proposal_from_dict(edit_proposal_to_dict(proposal))
        self.assertEqual(restored, proposal)

    def test_verification_round_trips_when_set(self):
        """
        Given a proposal with a non-default verification value
        When it is serialized and reconstructed
        Then the reconstructed proposal's verification survives, and the
            serialized dict carries it as a plain, branchable string --
            not folded into rationale prose.
        """
        base = self._distinctive_proposal()
        proposal = EditProposal(
            action=base.action,
            tool=base.tool,
            rationale=base.rationale,
            edits=base.edits,
            origin=base.origin,
            verification="safe",
        )
        data = edit_proposal_to_dict(proposal)
        self.assertEqual(data["verification"], "safe")
        restored = edit_proposal_from_dict(data)
        self.assertEqual(restored.verification, "safe")

    def test_verification_defaults_to_none(self):
        """
        Given a proposal built with no verification argument (e.g. a
            security-audit-produced EditProposal, which has no such concept)
        When it is serialized
        Then verification is None -- present in the dict, not omitted, so a
            consumer can rely on the key existing.
        """
        proposal = self._distinctive_proposal()
        self.assertIsNone(proposal.verification)
        data = edit_proposal_to_dict(proposal)
        self.assertIn("verification", data)
        self.assertIsNone(data["verification"])

    def test_the_serialized_form_survives_real_json(self):
        """
        Given the same proposal
        When it is serialized, rendered to JSON TEXT and read back
        Then json.dumps accepts it and the reconstruction still equals the original.

        The dict alone cannot show this: Path(Path(p)) == Path(p), so a provenance
        path left as a Path object round-trips through the dict and only fails at the
        file boundary --edits actually crosses.
        """
        proposal = self._distinctive_proposal()
        text = json.dumps(edit_proposal_to_dict(proposal))
        self.assertEqual(edit_proposal_from_dict(json.loads(text)), proposal)

    def test_a_minimal_dict_fills_the_documented_defaults(self):
        """
        Given a dict carrying only the two required keys, action and tool
        When edit_proposal_from_dict reads it
        Then rationale, edits and origin take their documented empty defaults.

        Called WITHOUT the optional keys on purpose -- a default is only exercised by
        its absence.
        """
        proposal = edit_proposal_from_dict({"action": ACTION_REMOVE, "tool": "Bash"})
        self.assertEqual(proposal.action, ACTION_REMOVE)
        self.assertEqual(proposal.tool, "Bash")
        self.assertEqual(proposal.rationale, "")
        self.assertEqual(proposal.edits, ())
        self.assertEqual(proposal.origin, "")

    def test_a_minimal_edit_dict_fills_its_pattern_defaults(self):
        """
        Given an edit dict with no removed_patterns and no added_patterns keys
        When rule_edit_from_dict reads it
        Then both tuples default to empty and the rest is reconstructed.
        """
        edit = rule_edit_from_dict(
            {
                "tool": "Read",
                "list_type": "deny",
                "provenance": {
                    "level": "user",
                    "source_type": "claude",
                    "file_format": "json",
                    "path": "/u/.claude/settings.json",
                    "specificity": 7,
                },
            }
        )
        self.assertEqual(edit.removed_patterns, ())
        self.assertEqual(edit.added_patterns, ())
        self.assertEqual(edit.list_type, "deny")
        self.assertEqual(edit.provenance.specificity, 7)

    def test_an_unrecognized_action_is_accepted_unvalidated(self):
        """
        Given a dict whose action is not one of ACTIONS
        When edit_proposal_from_dict reads it
        Then it is accepted verbatim, with no error and no normalization.

        Characterization: the action label is advisory, so an --edits file may carry
        a caption this module has no vocabulary for.
        """
        proposal = edit_proposal_from_dict({"action": "obliterate", "tool": "Bash"})
        self.assertEqual(proposal.action, "obliterate")


if __name__ == "__main__":
    unittest.main()
