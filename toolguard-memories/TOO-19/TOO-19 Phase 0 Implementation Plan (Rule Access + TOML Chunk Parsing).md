---
title: TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing)
type: note
permalink: toolguard/too-19/too-19-phase-0-implementation-plan-rule-access-toml-chunk-parsing
tags:
- task-memory
- TOO-19
---

> **STATUS 2026-07-27: HISTORICAL. Phase 0 is fully IMPLEMENTED (0a increments 0-10 and
> 0b increments 1-6, plus two Arnon-directed corrective changes). Read this for intent
> only -- the code, not this plan, is the source of truth. Two parts of it were
> deliberately overridden during implementation:**
>
> 1. **Multi-line structured entries were REVERSED.** Everything below that designs for,
>    or instructs support of, `{...}` entries spanning multiple lines (notably the
>    `rule_sort.py` / `annotate.py` / `reassemble_permissions_section` sections) is
>    **void**. Arnon ruled 2026-07-26 that TOML 1.0 conformance and not breaking stdlib
>    `tomllib` is a hard requirement: TOML forbids multi-line inline tables, so a
>    multi-line entry makes the *whole file* unparseable and silently drops every rule in
>    it -- including `hard_deny`. Structured entries are **single-line only**;
>    `_flatten_inline_table` was deleted and a specific diagnostic
>    (`_multiline_structured_entry_diagnostic`) now points at the offending line. The
>    readability cost was accepted explicitly.
> 2. **The silent-drop `isinstance(perm, str)` filter had FOUR sites, not the three this
>    plan enumerates.** The fourth (`toolguard_permissions()`) was found during
>    implementation and fixed as part of increment 1.
>
> Also added beyond this plan's scope, at Arnon's direction: the fail-open fix -- an
> unparseable config file used to drop its rules silently, and now clamps every decision
> to `ask` while naming the broken files. See
> [[TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report]].

Status: REVISION 2 (2026-07-25), incorporating Arnon's review of the original draft. Not
yet approved to implement -- no feature-coder dispatched, no code changed. Originally
drafted via Claude Code plan mode (plan mode exited unexpectedly before the normal
approval flow completed), then refined in conversation, then revised after review. Saved
here as the durable copy since Claude Code plan files are ephemeral; see
[[TOO-19 Structured Rule Entries - Rule-Match Enrichment]] for the requirements/decisions
this plan implements.

### What changed in revision 2

Review (Opus 5, verified against the code rather than assumed) found that the original
draft analyzed the READ paths thoroughly and the WRITE paths barely at all. Confirmed
findings, all accepted by Arnon:

1. **Increment 7 was aimed at the wrong file, and the real bug destroys data.**
   `config_divergence.get_toolguard_permissions()` already delegates to the centralized
   accessor, so there is no `TypeError` risk there. The real defect is
   `Configuration.toolguard_permissions()` (`config.py:1644`), which has its OWN
   `isinstance(perm, str)` silent drop that the original "concrete changes" list omitted.
   Chain: drop -> migration reports the native twin as divergent -> `write_toml_config` ->
   `reassemble_permissions_section` emits only patterns present in `new_permissions` ->
   **the structured entry is deleted from the user's file**. `auto_migrate.py:198` runs
   this unattended. Strictly worse than the silent-match-drop this phase exists to fix.
2. **The maintenance write path crashes.** `rule_apply.py::_current_permissions` reads raw
   file lists (dicts survive) -> `write_toml_config` -> `sort_patterns` ->
   `get_tool_priority(dict)` -> `tool_priorities.get(dict)` ->
   `TypeError: unhashable type: 'dict'`. The original plan covered
   `with_layer_rules_replaced` (analysis only, synthetic `Configuration`) but not the
   actual file writer.
3. **Phase 0b understated `reassemble_permissions_section`.** Its correlate-by-key logic
   is not the problem; the PAYLOAD TYPE is. `new_permissions` is `Dict[str, List[str]]`
   end-to-end, and reassemble drops anything absent from it and synthesizes a plain
   `"..."` line for anything missing from `rule_lines`.
4. **Parser signature conflated two jobs** -- fixed by splitting into `normalize_entry`
   (shape, tool-agnostic, wrapper-intact) and `entries_for_tool` (tool scoping).
5. **Flat-hashable-forever dropped** -- see the revised design section.
6. **JSON configs were unaddressed** -- added, and they are much cheaper than TOML (no
   comments to preserve, stdlib `json` needs no custom parsing or reassembly).
7. **hard_deny enrichment IS meaningful** (Arnon) -- see that section.

---

# TOO-19 Prerequisite Phases: Rule-Access Refactor + TOML Chunk-Parsing Support

## Context

TOO-19 proposes letting a matched permission rule inject `additionalContext` back into
Claude's context (verified feasible against the real Claude Code hooks API this session).
Building that on today's codebase is unsafe: every allow/deny/ask entry is assumed to be a
bare `str` in ~9+ places, and anything that isn't a string is **silently dropped with zero
warning** today (confirmed in `config.py`, `config_validation.py`) -- including from DENY
lists. Introducing an object-form rule entry without fixing this first would make that
latent bug live and dangerous.

Per this session's design discussion (recorded in basic-memory,
`toolguard/TOO-19/TOO-19 Structured Rule Entries - Rule-Match Enrichment.md`), we agreed to
do two prerequisite phases before touching the feature itself:

- **Phase 0a**: centralize permission-entry parsing so the str-only assumption is removed
  and malformed entries are surfaced (not silently dropped).
- **Phase 0b**: teach the separate, comment-preserving TOML text parser (used by
  `/sort-permissions`, maintenance's annotation writer, and `#NOSECURITY` comment
  recovery) to handle multi-line structured entries, without adding a runtime dependency
  or building a full PEG-based TOML parser (both considered and rejected this session).

**Both phases must be TDD (red-green-refactor), with review of the diff after every single
cycle, and must leave the existing test suite fully green throughout.** No feature (Phase
1 / `additionalContext` itself) starts until both are done and reviewed. This plan covers
Phase 0a and 0b only.

## Phase 0a: Rule-Access Refactor (remove the str assumption)

### Design

Add a `RuleEntry` frozen dataclass to `toolguard/config.py`. **Revised in revision 2** --
the original draft stored metadata as a tuple of flat primitives to get hashability for
free; that bought a `set()` convenience at the price of a permanent schema constraint.
Reviewed sketch (approved shape, comments are part of the design):

```python
PATTERN_KEY = "match"          # {match = "Bash(...)", additionalContext = "..."}
KNOWN_ENRICHMENT_KEYS = frozenset()   # Phase 1 adds "additionalContext"; auto-mode adds its flag

@dataclass(frozen=True)
class RuleEntry:
    """One allow/deny/ask entry, plain-string or structured form.

    Format-agnostic: the same type comes out of TOML, JSON, and
    synthesized-by-tooling entries, so every consumer sees one shape.
    """

    # Wrapper-INTACT, exactly as written: "Bash([regex]^git .*)".
    # Deliberately NOT stripped: permission_layers() is the ONLY consumer that
    # wants the wrapper-free body and it strips at its own call site. Every
    # other consumer (toolguard_permissions, validate_permissions,
    # with_layer_rules_replaced, the whole rule_sort/write path) is
    # tool-agnostic and needs the wrapped form. Storing the stripped form is
    # what made the original single-parser signature wrong.
    pattern: str

    # Plain Mapping, NOT a tuple of flat primitives. Constraining every future
    # enrichment value to str/int/float/bool/None permanently forbids the first
    # field that wants a list (applies_to = ["Bash", "Read"]) or a sub-table,
    # in a mechanism explicitly designed as a general extension point for later
    # tickets. Hashability is recovered via identity() instead.
    # Always built as MappingProxyType(...) by the parser, so "frozen" is not a
    # lie: neither the field nor its contents can be rebound or mutated.
    metadata: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

    # The exact source value this was parsed from (str, or the dict).
    # Lets the write path re-emit an UNTOUCHED entry verbatim instead of
    # re-rendering it -- this is what makes "maintenance tooling must not
    # destroy enrichment on unrelated edits" hold byte-for-byte WITHOUT
    # threading raw str-or-dict unions through the writers by hand.
    # compare=False: formatting is not identity. An entry written as a
    # multi-line table equals the same entry written inline.
    raw: object = field(default=None, compare=False, repr=False)

    @property
    def is_structured(self) -> bool:
        return isinstance(self.raw, dict)

    def identity(self) -> Tuple[str, str]:
        """Canonical hashable identity: (pattern, canonicalized metadata).

        Use identity() -- not .pattern -- wherever two entries must be
        distinguished by their ENRICHMENT as well as their pattern:
        consolidate.py / redundancy.py dedup, where merging a plain entry into
        an enriched one silently drops the context.

        Use .pattern wherever the question is "is this the same RULE",
        regardless of enrichment: config_divergence / migration, where a
        pattern with context on one side and without on the other is NOT a
        divergence.

        The two are deliberately DIFFERENT comparisons -- see "'Same rule'
        means two things" below.
        """
        return (self.pattern, json.dumps(dict(self.metadata), sort_keys=True, default=str))

    def __hash__(self) -> int:
        # set(entries) works without constraining metadata value types. The
        # dataclass-generated __hash__ would raise TypeError the moment a
        # metadata value is a list.
        return hash(self.identity())

    def to_source(self) -> object:
        """The value to write back into a config file (TOML table / JSON object).

        Returns `raw` verbatim for an unmodified entry -- the round-trip
        guarantee. Only synthesized/edited entries are re-rendered.
        """
        if self.raw is not None:
            return self.raw
        if not self.metadata:
            return self.pattern
        return {PATTERN_KEY: self.pattern, **dict(self.metadata)}
```

**Two functions, not one** (the conflated-jobs split):

- `normalize_entry(raw, is_native) -> Tuple[Optional[RuleEntry], Tuple[Issue, ...]]` --
  shape normalization ONLY, tool-agnostic, wrapper-intact. The single chokepoint that
  replaces every scattered `isinstance(perm, str)` check. Returns `None` plus issues (never
  a silent drop) when the element is unusable: wrong type, dict missing `match`, `match`
  value not wrapper-shaped, or a dict entry in a native layer.
- `entries_for_tool(entries, tool_name) -> Tuple[RuleEntry, ...]` -- tool scoping ONLY.
  Wrapper stripping stays at the `permission_layers()` call site, its only consumer.

### "Same rule" means two things -- document it, do not "fix" it

`"Bash(git push:*)"` and `{match = "Bash(git push:*)", additionalContext = "..."}` are:

- the SAME rule to divergence/migration (compare `.pattern`) -- otherwise migration
  re-adds the native twin forever;
- DIFFERENT rules to consolidate/redundancy (compare `identity()`) -- otherwise merging
  drops the context.

Both are correct for their purpose. Unwritten, this reads as an inconsistency and someone
later "fixes" one of them. The two accessors are named distinctly precisely so the call
site reads as a deliberate choice; each call site carries a one-line comment saying which
comparison it wants and why.

### Same-pattern merge rules (Arnon, 2026-07-25 -- supersedes plain `identity()` dedup)

`identity()` answers "are these literally the same entry", which is the right fast path but
NOT the whole consolidation story. Arnon specified the actual semantics; encode them as a
dedicated `merge_entries(entries) -> MergeOutcome` helper rather than as ad-hoc set logic
inside `consolidate.py`/`redundancy.py`, so the rules live in one testable place.

**Sorting** cares about `.pattern` ONLY. No metadata involvement whatsoever. (This is the
third distinct comparison in the codebase -- see the two above -- and the simplest.)

**Consolidation**, for a group of entries sharing the same `.pattern`:

1. **Bare string vs. structured** -> **drop the bare string.** The structured entry is
   clearly the intended rule; the bare one adds nothing. Not a conflict, not a warning --
   a clean win for the structured entry. (Note this is a genuine simplification over the
   original draft, which would have kept both as "distinct" under `identity()`.)
2. **Multiple structured entries, metadata compatible** -> **trivial union merge.**
   "Compatible" means: for every key present in more than one entry, all its values are
   equal; the remaining keys are disjoint. Result is the union of all key/value pairs, no
   duplicates. No user interaction needed.
3. **Multiple structured entries with a CONTRADICTION** (same key, different values) ->
   **keep them separate and alert the user.** Do not pick a winner, do not merge, do not
   silently drop either side. Surface it as a finding, and optionally write an inline
   `# toolguard:` comment marking the confusion so it is visible in the file itself (the
   `annotate.py` machinery this plan already touches in Phase 0b is the natural vehicle;
   treat the comment as a nice-to-have, the alert as mandatory).

Note that case 3 is the only one needing user attention, and cases 1 and 2 resolve
automatically -- which is what keeps this from becoming an interactive-prompt burden in the
maintenance skill. It also refines increment 9's `rule_apply` guard: the guard fires only
on case 3 (a genuine contradiction), not on every entry that happens to carry metadata,
which would have been needlessly conservative.

**Tests this needs** (increment 6): one per case -- bare+structured collapses to the
structured one; disjoint-key structured entries union cleanly; identical-value overlapping
keys union cleanly; same key/different value stays separate AND raises the alert;
three-way group mixing all of the above resolves correctly.

**Naming call:** the structured entry's pattern-key is `match` (not `rule`) -- e.g.
`{match = "Bash([regex]^grep .*)", additionalContext = "..."}`. CONFIRMED by Arnon at the
revision-2 review.

**Known-keys registry:** a small module-level set (starts as just `{"match"}`) that Phase 1
(and later tickets, e.g. the auto-mode per-rule flag) extend by adding one entry. Any OTHER
key present in a structured entry is a WARNING-level validation issue (typo protection),
not an error -- forward-compatible with a newer toolguard version's fields being read by an
older one.

**Backward compatibility, by design:** `ToolPatternLayer.allow/deny/ask` KEEP returning
`Tuple[str, ...]` of pattern strings exactly as today, built from `RuleEntry.pattern`. This
is the key move that keeps this phase small: matching (`permissions.py`, `resolve.py`,
`compound.py`), provenance (`_provenance_for_pattern`), and every read-only tool consumer
(`consolidate.py`, `clarity.py`, `rule_apply.py`, `takeover_audit.py`, `installer.py`,
`config_access.py::per_layer_rules`) needs **no changes** -- they just start seeing the
correct, complete pattern list (today's silent-drop bug, fixed as a side effect). Add
`allow_entries/deny_entries/ask_entries: Tuple[RuleEntry, ...]` fields alongside the
existing string tuples, for Phase 1 to look up metadata by the winning pattern later.

**Native-layer gating (toolguard-only restriction), folded in from Phase 1's planning
gap.** Structured entries are a toolguard extension and must never be interpreted from a
native Claude `settings.json` layer (`layer.is_native`), per this session's locked-in
decision. `normalize_entry` therefore takes the layer's `is_native` flag as a
parameter: when `is_native` is True, a dict-shaped raw entry is rejected (treated the same
as an unparseable entry -- `None` back to the caller, plus a `warning`-level validation
issue "structured rule entries are ignored in native Claude settings files") rather than
being parsed into a `RuleEntry` with metadata. A plain string entry in a native layer
parses exactly as before (`RuleEntry(pattern, {})`), unaffected. This mirrors the existing
`if layer.is_native: continue` guard already used elsewhere in this file (e.g. the
`hard_deny()` extraction at line 1155, and the takeover-ignored-patterns filter at line
1218) -- same posture, applied to the new structured-entry path. This was flagged during
Phase 1 planning as a gap in this plan (parsing would otherwise happily accept a
dict-shaped entry from any layer, native or not) and is now closed here rather than left
for Phase 1 to patch retroactively, since it's about which shapes are valid WHERE, not
about the `additionalContext` feature itself.

### Confirmed safe by design (no changes needed) -- from a full-repo consumer sweep

A repo-wide sweep (Explore agent, this session) confirmed the "keep `.allow/.deny/.ask` as
plain string tuples" design decision insulates the entire matching pipeline and most
tooling automatically, since they all consume the central `ToolPatternLayer`/`LayerRules`
accessor rather than raw layer content: `toolguard/permissions.py` (`match_command`,
`check_hard_deny`, `check_permission`), `toolguard/resolve.py` (file-path matchers),
`toolguard/compound.py` (explicitly typed `List[str]`; its own test suite,
`test_compound.py`, calls it with bare Python list literals -- no `Configuration`/TOML
involved at all, so genuinely untouched), `toolguard/tools/hierarchy.py`
(`find_cross_layer_redundancies`), `toolguard/tools/danger.py` (`_run_detectors_for_tool`),
`toolguard/tools/security_audit.py` (`--with-context` JSON serialization of
`list(lc.allow)` etc. -- JSON-safe as long as `lc` is a `LayerRules`, which it is),
`toolguard/tools/mining.py` (`evaluate_added_allow_rule` only ever SYNTHESIZES new
plain-string suggestions, never reads structured entries), `toolguard/tools/self_permission.py`,
`uninstall_readiness.py`, `recommended_protections.py` (declarative literal tables of
hardcoded plain-string suggestions, output-only). None of these need code changes; worth a
regression-test pass only.

### The write paths: two confirmed defects the original draft missed

**Superseded:** the original draft's "one real new risk found: `config_divergence.py`"
section was WRONG. `get_toolguard_permissions()` (`config_divergence.py:161`) already
delegates to `Configuration.toolguard_permissions()`, so no `TypeError` is reachable there
and that increment would have been a no-op verification. Both real defects are downstream,
in code the draft never inspected. Verified against the source, not inferred.

#### Defect W1 -- silent DELETION of structured entries by migration (severity: high)

`Configuration.toolguard_permissions()` (`config.py:1644`) carries its own
`isinstance(perm, str) and perm not in result[perm_type]` filter -- a THIRD silent-drop
site the draft's concrete-changes list omitted (it covered only `permission_layers()` and
`hard_deny()`). Note it returns WRAPPER-INTACT strings, unlike `permission_layers()`, which
is why `RuleEntry.pattern` is now defined wrapper-intact.

The chain, all confirmed by reading the code:

```
Configuration.toolguard_permissions()   config.py:1644     drops the structured entry
  -> get_toolguard_permissions()        config_divergence.py:161
  -> find_divergent_patterns()          config_divergence.py:198-202
                                        native twin now looks "divergent"
  -> migrate() -> write_toml_config(target, merged_perms)
                                        migrate_permissions.py:876
  -> reassemble_permissions_section()   rule_sort.py:310-330
                                        emits ONLY patterns present in new_permissions
  => the structured entry is GONE from the user's config file
```

`auto_migrate.py:198` drives this path unattended. So the first auto-migration after a user
adds an enriched rule silently deletes it. This is strictly worse than the silent-match-drop
this whole phase exists to fix -- that one loses enforcement until corrected; this one
destroys the user's authored text.

#### Defect W2 -- the maintenance write path crashes (severity: medium)

`rule_apply.py::_current_permissions` (lines 139-143) reads the raw file lists
(`list(perms.get("allow", []) or [])`), so dict entries DO survive into the write payload.
Then:

```
write_toml_config -> reassemble_permissions_section -> sort_patterns
  -> get_tool_priority(entry)           rule_sort.py:55-58
     "(" in dict          -> False (checks KEYS, does not raise)
     tool_priorities.get(dict)  -> TypeError: unhashable type: 'dict'
```

`write_json_config` sorts the same way, so the JSON path crashes identically. The draft
covered `with_layer_rules_replaced` -- but that only builds a synthetic `Configuration` for
ANALYSIS; the actual file writer was never in scope. Net effect: the first time the
maintenance skill applies an approved rule edit to a file containing a structured entry, it
raises.

#### Why Phase 0b's "small adjustment" framing was wrong

`reassemble_permissions_section`'s correlate-by-pattern-string-key logic is not the
problem. The PAYLOAD TYPE is: `new_permissions` is `Dict[str, List[str]]` end-to-end, and
reassemble both (a) drops anything absent from it and (b) synthesizes a plain `"..."` line
for anything missing from `rule_lines`. So a structured entry either never arrives (W1,
deleted) or arrives as a dict (W2, crash).

**Fix shape, deliberately NOT convoluted** (Arnon flagged the phrase "threading entries
through the whole write path" as a convolution risk -- this is the answer): do NOT thread
`str`-or-`dict` unions through the writers. Change the payload type ONCE, from
`Dict[str, List[str]]` to `Dict[str, List[RuleEntry]]` -- a single uniform type end-to-end
-- and have each writer call `entry.to_source()` at the one point where it actually emits.
`sort_patterns` keys off `entry.pattern`. Untouched entries come back verbatim because
`raw` is returned as-is. That is FEWER branches than today's implicit "sometimes a str,
sometimes a dict, depending which reader you came through", not more.

#### Deterministic helper for the maintenance skill (Arnon: "use your judgement")

`rule_apply.py` already IS the deterministic (non-AI) apply path, so extend it rather than
adding a parallel helper. One behavioural addition: when a consolidation/redundancy
proposal targets an entry carrying metadata, `rule_apply` must either carry that metadata
onto the merged entry or REFUSE the proposal with an explicit
`"would lose rule enrichment"` skip reason -- never apply it and drop the context. That
skip reason surfaces through the existing `FileChange` reporting, so the maintenance skill
tells the user why an otherwise-valid consolidation was declined. This is the deterministic
guarantee the skill needs; no AI judgement involved.

`toolguard/tools/edit_proposal.py::apply_edits()` also does `set(edit.removed_patterns)`,
but `RuleEdit.removed_patterns`/`added_patterns` are typed `Tuple[str, ...]` and populated
by upstream analysis (`redundancy.py`/`consolidate.py`, which already read through
`LayerRules.allow` -- plain strings) -- expected safe by construction, confirm via
regression test rather than a code change.

### Concrete changes

1. `toolguard/config.py`: `RuleEntry` + `normalize_entry` (takes `layer.is_native` and
   rejects dict-shaped entries when True, emitting the native-layer-rejection validation
   warning) + `entries_for_tool`, wired into `permission_layers()` (allow/deny/ask
   extraction, ~line 1177-1249) and the `hard_deny()` extraction (~line 1140-1176).
1b. `toolguard/config.py::toolguard_permissions()` (~line 1644) -- **added in revision 2**,
   the third silent-drop site (defect W1). Route through `normalize_entry`; keep returning
   wrapper-intact values. Its return type widens from `Tuple[str, ...]` per key to
   `Tuple[RuleEntry, ...]` per key, since every consumer of it feeds the write path.
2. `toolguard/config_validation.py::validate_permissions`: use the shared parser; emit an
   `error`-level `Issue` for entries that fail to parse at all (dict with no valid pattern
   key, or an unrecognized raw type), and a `warning`-level `Issue` for unrecognized extra
   keys in an otherwise-valid structured entry. **No new surfacing plumbing needed** --
   `Configuration.validation_issues()` already flows into `hook.py`'s once-per-session
   `record_validation_issues`-style routine (line ~103), which logs errors/warnings to the
   existing log streams automatically.
3. `toolguard/tools/config_access.py::with_layer_rules_replaced` /
   `with_layer_allow_replaced`: currently does
   `[p for p in target_list if p not in wrapped_removed] + wrapped_added` directly against
   the raw parsed list, which would silently flatten any UNTOUCHED structured entry to a
   plain string membership test. Fix: parse each `target_list` item via the shared parser to
   get its `.pattern` for the removal-membership check, but keep the ORIGINAL raw item (str
   or dict) unchanged in the output list when it isn't being removed. This is what makes
   "maintenance tooling must not destroy enrichment on unrelated edits" hold.
4. Audit (not necessarily change) `consolidate.py` / `redundancy.py`'s dedup/merge logic:
   two entries with the same `.pattern` but different `.metadata` (or one enriched, one not)
   must not be silently merged without flagging the metadata loss. feature-coder reads
   both files first and reports which need real changes vs. are already safe (they may
   only ever compare pattern strings today, in which case a small equality-check fix is
   needed).
5. **Added in revision 2 -- the write path.** `rule_sort.py::sort_patterns` /
   `get_tool_priority` (key off `entry.pattern`), `migrate_permissions.py::
   generate_permissions_section` / `write_toml_config` / `write_json_config`, and
   `rule_apply.py::_current_permissions` / `_render_via_writer`: widen the permissions
   payload from `Dict[str, List[str]]` to `Dict[str, List[RuleEntry]]` and emit via
   `entry.to_source()`. Closes defects W1 and W2.
6. **Added in revision 2 -- `rule_apply.py` enrichment guard.** A proposal that would merge
   away an entry carrying metadata is either carried forward or refused with a
   `"would lose rule enrichment"` skip reason. Never applied-and-dropped.

### TDD increments

**Review protocol (revised 2026-07-25, Arnon):** intermediate reviews between TDD
increments are done by the MAIN orchestrating agent, or by an Opus subagent it spawns --
not by Arnon. Human review happens only BETWEEN PHASES (end of 0a, end of 0b). Each
increment is still a separate feature-coder dispatch with a review before the next is
dispatched; the reviewer is just an agent rather than Arnon.

Existing test files to route new tests into (confirmed by the consumer sweep, so
feature-coder extends the right file instead of guessing):

0. **The unrelated rules-directory fix** (see the section near the end of this plan:
   `_rules_dirs()` scanning `~/.toolguard/rules/` + the `_level_for_path` anchor tuple).
   Completely independent of everything else here -- Arnon folded it into this ticket only
   because it is too small to justify its own. Do it FIRST, as its own increment, so the
   `gh.rules.toml` symlink workaround can be removed early and it never entangles with the
   `RuleEntry` work.
1. `RuleEntry` + `normalize_entry` + `entries_for_tool` as a pure, standalone unit (new
   direct tests, likely a new small test file or a new class in `test/unit/test_config.py`):
   plain string in/out, dict-with-`match`-key in/out, unrecognized-key warning case,
   malformed shapes -> `None`; PLUS the native-layer gating case: a dict-shaped entry with
   `is_native=True` -> `None` + warning issue, while a plain string with `is_native=True`
   still parses normally. PLUS the type-contract tests that protect the design decisions:
   `identity()` distinguishes same-pattern/different-metadata; `.pattern` does not;
   `set(entries)` works with a LIST-valued metadata field (proves the flat-primitive
   constraint really is gone); `to_source()` returns `raw` verbatim for a parsed entry and
   synthesizes only for a constructed one.
2. Wire into `permission_layers()` + add `*_entries` fields to `ToolPatternLayer`. Extend
   `test/unit/test_configuration.py::TestPermissionLayers` (~10 existing tests, builds
   `Configuration(layers=(ConfigLayer(...MappingProxyType({"permissions": {"allow": [...]}})...` --
   the new tests add a structured-entry dict literal into that same fixture shape). Tests:
   a mixed plain-string + structured config has ALL patterns present in
   `.allow`/`.deny`/`.ask` (proves the silent-drop is fixed); `*_entries` populated
   correctly and in the same order; a structured entry placed in a native (`claude`) layer
   is dropped from `*_entries`/ignored as structured (its pattern, if it parses as a bare
   pattern, is NOT treated as enriched) -- confirms the toolguard-only restriction holds at
   the earliest possible point rather than relying on Phase 1 to filter it out later.
3. Wire into `hard_deny()` extraction. Extend `test/unit/test_hard_deny.py` (~20 existing
   tests, mixes a `_layer()` direct-construction helper with real-file isolation tests).
   **Revision 2 (Arnon):** enrichment on a hard-deny entry IS meaningful and must be
   accepted, not accepted-and-ignored. A hard deny is exactly where an
   `additionalContext` earns its keep -- reinforcing a CLAUDE.md directive at the moment
   it is violated, and offering a concrete alternative ("I already told you not to use
   this command; use this one instead"). So `hard_deny()` gains `*_entries` alongside its
   pattern tuples on the same terms as `permission_layers()`, and Phase 1 wires the
   injection. Nothing here is hard-deny-specific beyond that.
4. `config_validation.py` + `Configuration.validation_issues()`. Extend
   `test/unit/test_toml_config.py::TestValidatePermissions` (~6 existing tests, plain dict
   literals, no file I/O): one test per validation branch (malformed entry -> error,
   unrecognized key -> warning, valid structured entry -> no issue), plus one test
   confirming the issue reaches `hook.py`'s log routing.
5. `with_layer_rules_replaced`/`with_layer_allow_replaced` fix. Extend
   `test/unit/test_tools_edit_proposal.py` and/or `test/unit/test_tools_consolidate.py`
   (confirmed as where this function is actually exercised today, NOT
   `test_tools_config_access.py`). Test: removing/adding a plain pattern in a list that
   also contains an untouched structured entry leaves that entry's dict form
   byte-identical in the resulting `Configuration`.
6. `consolidate.py`/`redundancy.py` audit + fix. Implement `merge_entries()` per the
   "Same-pattern merge rules" section (bare-loses-to-structured; compatible metadata
   unions; contradictions stay separate + alert) rather than raw `identity()` set logic --
   `identity()` remains the "literally identical" fast path inside it. Each call site
   carries a one-line comment naming which of the THREE comparisons it wants
   (`.pattern` for sorting/divergence, `identity()` for exact-duplicate detection,
   `merge_entries()` for consolidation) and why. Plus confirmation (existing tests
   unchanged/still green) that `takeover_audit.py` and `installer.py` need no changes. NOTE: `rule_apply.py` was listed here as needing no
   changes -- **that was wrong**, see increments 8/9.
7. `config_divergence.py` -- **rescoped in revision 2.** The original "does it read raw
   layer content?" question is answered: it does NOT, it already delegates to the
   centralized accessor, so there is no `TypeError` to fix here. What remains is a
   regression guard on the comparison SEMANTICS after `toolguard_permissions()` starts
   returning `RuleEntry`: `find_divergent_patterns` compares by `.pattern` alone --
   deliberately pattern-only, NOT `identity()`, because a rule with metadata on one side
   and none on the other is the same rule, not a divergence. Extend
   `test/unit/test_config_divergence.py`. Tests: (a) a structured entry on the toolguard
   side does not raise; (b) same pattern, metadata on one side only -> NOT divergent;
   (c) a structured entry's pattern is present in the comparison at all (the W1
   silent-drop regression guard, at its source).
8. **New (revision 2) -- write-path payload widening.** `sort_patterns`/`get_tool_priority`
   key off `entry.pattern`; `generate_permissions_section`, `write_toml_config`,
   `write_json_config` emit via `entry.to_source()`; `rule_apply._current_permissions`
   returns entries. Extend `test/unit/test_migration.py`, `test/unit/test_tools_sorters.py`,
   `test/unit/test_tools_rule_apply.py`. **The headline test, the one that would have
   caught all of this:** a full `migrate()` round-trip over a config file containing a
   structured entry leaves that entry BYTE-IDENTICAL, including its formatting, its
   position after sorting, and its comments. Plus: `sort_patterns` over a list containing a
   structured entry does not raise (W2); a structured entry survives an unrelated
   `rule_apply` edit to a different rule in the same file (W1).
9. **New (revision 2) -- `rule_apply` enrichment guard.** Refined 2026-07-25 by the
   merge-rules decision: the guard fires only on a genuine CONTRADICTION (case 3), not on
   every entry carrying metadata. Cases 1 and 2 resolve automatically and apply normally.
   A contradicting proposal is refused with a `"would lose rule enrichment"` skip reason
   surfaced through `FileChange`. Extend `test/unit/test_tools_rule_apply.py`: proposal
   producing a contradiction -> skipped with that reason, file unchanged; proposal
   producing a clean union -> applies, merged metadata correct; proposal targeting only
   plain entries in a file that also holds an enriched one -> applies normally, enriched
   entry untouched.

## Phase 0b: TOML Chunk-Parsing Support (sort/annotate/comment-recovery)

### Design

`toolguard/rule_sort.py::parse_permissions_section_with_comments` is a hand-rolled,
comment-preserving parser used because stdlib `tomllib` strips comments -- it exists
specifically to support `/sort-permissions`, `annotate.py` (maintenance's inline
`# toolguard:` comment writer), and `config_access.py::_layer_comment_map` (`#NOSECURITY`
recovery for security-audit). It currently assumes **one pattern per physical line**.
Considered and rejected this session: adding a comment-preserving TOML library
(`tomlkit`) -- violates the project's zero-runtime-dependency policy; a full PEG-grammar
TOML sub-parser (mirroring the Bash grammar) -- more engineering than the bounded problem
justifies; mandating single-line structured entries -- rejected on human-readability
grounds.

**Adopted approach:** relax the invariant to "each new top-level array entry starts on a
new line; multi-line spans are legal only for structured `{...}` entries," and split the
work into a small, reusable primitive plus three call-site adaptations:

1. A new shared boundary scanner (in `rule_sort.py`) that finds top-level array-element
   boundaries via a single linear pass tracking quote-state (`"..."`/`'...'`) and
   brace-depth (`{...}`), splitting only on top-level commas. Tool-name-agnostic (no need
   to enumerate `Bash(`/`Read(`/etc., which would be brittle against
   `additional_supported_tools`).
2. Per chunk, extract the pattern value via stdlib `tomllib`: wrap the chunk
   (`x = [ <chunk> ]`) and parse it, instead of the current hand-rolled
   double/single-quote regex (which is already somewhat fragile per its own docstring
   caveats -- this retires that fragility as a side effect, for both plain-string and
   structured chunks alike).
3. `reassemble_permissions_section` -- **revision 2 correction: this is NOT "only a small
   adjustment".** Its correlate-by-pattern-string-key logic (`rule_lines[value]`,
   `rule_comments[value]`) does generalize as the draft said, but that was never the
   problem. The problem is the payload type (`Dict[str, List[str]]`), handled by increment
   8 of Phase 0a. Once entries arrive as `RuleEntry`, the change HERE really is small:
   key off `entry.pattern`, and emit `entry.to_source()` in the synthesize-from-scratch
   fallback instead of the string-only `f'  "{escaped}",'`. Sequencing note: Phase 0a
   increment 8 must land before this, or this increment has nothing to consume.
   Round-tripping an existing structured entry is the requirement; AUTHORING a well-formed
   multi-line structured entry from scratch is still a Phase 1 concern, but the fallback
   must at minimum emit a VALID single-line inline table via `to_source()` rather than
   silently stringifying a dict.
4. `annotate.py`'s `_rule_line_patterns`/`annotate_section_text` currently iterate
   `section_text.split("\n")` one physical line at a time and key off exact line text --
   this breaks for a multi-line chunk. Switch to iterating chunks (via the shared
   scanner), inserting the generated `# toolguard:` comment above the chunk's first line.
5. `config_access.py`'s `_inline_comment_after_pattern` currently assumes `content` (a
   rule's raw text) is a single line when finding a trailing `#` comment via
   `line.rfind(...)`. Adapt it to operate on the chunk's LAST line, where a trailing
   inline comment would actually sit.

`find_section_boundaries` (finds the `[permissions]` section itself) needs no change --
it already operates at a coarser, unaffected granularity.

### JSON configs (added in revision 2)

The original plan never mentioned `toolguard_hook.json`, which is a first-class supported
format. Confirmed impact: `write_json_config` calls `sort_patterns` on the same payload, so
it hits defect W2 identically.

**Arnon's framing, accepted: the JSON side is much cheaper than TOML.** JSON has no comment
support, so there is nothing to preserve and no custom parsing or reassembly to write --
stdlib `json` round-trips a `{"match": ..., "additionalContext": ...}` object natively.
Concretely, the JSON side needs only:

- `write_json_config`: sort via `entry.pattern`, serialize via `entry.to_source()` (which
  returns the original dict, so `json.dump` handles it with no special casing);
- `rule_apply._current_permissions` already reads JSON lists generically -- covered by the
  same widening as TOML, no JSON-specific branch;
- `normalize_entry` is format-agnostic by construction, so the READ side needs nothing.

None of the Phase 0b chunk-scanner work applies to JSON at all. Budget this as one small
increment, not a parallel workstream.

### A note on test coverage before starting

`parse_permissions_section_with_comments` and `reassemble_permissions_section` currently
have **no direct unit tests** -- only indirect coverage via `test_tools_annotate.py` and
`test_tools_config_access.py`. Before refactoring them, add direct characterization tests
locking down today's single-line behavior, so the red-green cycle has a real regression
baseline independent of the two indirect consumers.

### TDD increments

1. New `test/unit/test_rule_sort.py`: characterization tests for CURRENT
   `parse_permissions_section_with_comments`/`reassemble_permissions_section` behavior
   (plain strings, comments, both quote styles) -- no production code changes yet.
2. New shared boundary-scanner function, with direct unit tests: plain strings,
   single-line and multi-line `{...}` entries, commas/braces inside quoted strings.
3. Rewrite `parse_permissions_section_with_comments` to use the scanner + per-chunk
   `tomllib` value extraction. Existing characterization tests from #1 must stay green;
   add new tests for multi-line structured entries with comments preserved.
4. Adjust `reassemble_permissions_section` for multi-line chunk content. Round-trip
   tests: unchanged input -> byte-identical output; sort-and-reassemble preserves a
   structured entry verbatim while reordering it.
5. Adapt `annotate.py` to chunk-based iteration. Existing `test_tools_annotate.py` suite
   must stay green; add tests for annotating around a multi-line structured entry.
6. Adapt `config_access.py::_inline_comment_after_pattern`/`_layer_comment_map`.
   Existing `test_tools_config_access.py` must stay green; add tests for `#NOSECURITY`
   and comment extraction on a structured entry.
7. **New (revision 2) -- JSON.** `write_json_config` sorts/serializes via `RuleEntry`.
   Extend `test/unit/test_migration.py` (JSON write tests) and
   `test/unit/test_tools_rule_apply.py`: a `toolguard_hook.json` holding a structured entry
   round-trips through migrate and through an unrelated `rule_apply` edit with the entry
   intact. Small -- see the JSON section above for why.

### Coverage requirement (revision 2, Arnon)

This plan already documents that `parse_permissions_section_with_comments` and
`reassemble_permissions_section` have NO direct unit tests, and the write path
(`write_toml_config`/`write_json_config`/`generate_permissions_section`) turned out to be
where both real defects were hiding -- precisely because nobody had looked at it. Coverage
here is not a nice-to-have; the gap IS the root cause.

Requirement: at the end of each phase, run `uv run python tools/coverage_stdlib.py` and
check `cover/` for `>>>>>>` (never-executed) lines in the touched modules --
`config.py`, `config_validation.py`, `rule_sort.py`, `config_access.py`,
`migrate_permissions.py`, `rule_apply.py`, `config_divergence.py`. Any uncovered NEW line
must be either tested or explicitly justified in the phase-end review. Pre-existing
uncovered lines in those files are noted but not required to be closed (scope control).

## Process (both phases)

- feature-coder implements ONE increment at a time via strict red-green-refactor (failing
  test first, confirm it fails for the right reason, minimal code to pass, refactor while
  green). Multiple feature-coder invocations per phase, not one large one.
- **Review protocol (revision 2, Arnon):** the diff after each increment is reviewed by the
  MAIN orchestrating agent, or by an Opus subagent it spawns -- NOT by Arnon. Arnon reviews
  only BETWEEN PHASES (end of 0a, end of 0b). This keeps the increment cadence fast while
  preserving the phase-level human gate.
- After every increment: full suite green
  (`uv run python -m unittest discover -s test -t .`) and `uv run ruff check .` clean.
- **`ruff format`: format ONLY the files you touched, never repo-wide.** Corrected
  2026-07-25 after Arnon challenged the earlier "never run ruff format" rule and I verified
  it empirically (ruff 0.15.14, Python 3.14.5). The old rule was wrong on two of three
  counts: there is NO single-quote-to-double-quote churn (the codebase is already
  double-quoted; 27 of 4791 diff lines contain a single quote at all), and
  `except (A, B):` -> `except A, B:` is NOT corruption -- `requires-python = ">=3.14"` and
  PEP 758 make the unparenthesized form valid and identical in meaning. Only the "no
  `[tool.ruff]` config" part was true.
  The real issue is diff pollution: 56 of 117 files have drifted from ruff's defaults
  (purely line-wrapping at 88 chars), so a repo-wide `ruff format .` would dump ~4800
  reflow lines on top of this ticket's diff and make review impossible. ruff's DEFAULTS
  are correct for this repo (61 files already conform exactly; 88 is the best-fitting
  line-length -- tested 88/90/100/120, higher values reformat more).
  So: feature-coder formats the files it edited, `ruff check .` clean, no repo-wide format.
  Adding `[tool.ruff] line-length = 88` + a pinned ruff + one intentional format commit is
  a worthwhile SEPARATE task -- explicitly out of scope for TOO-19, since it would collide
  with this ticket's diff. See [[project_toolguard_dev_tooling]].
- Any new test touching `load_configuration()`/the discovery path must follow
  `test/unit/CLAUDE.md`'s isolation checklist (`ConfigIsolationMixin`) -- this has caused
  real, confirmed test failures before when skipped.
- Every new test carries a Given/When/Then BDD docstring (project convention).
- End of each phase: run `/code-review` on the phase's changes before moving on (matches
  this project's existing phase-end-gate practice).

## Explicitly out of scope for this plan

The `additionalContext` feature itself (Phase 1: object-form entries actually usable in
allow/deny/ask, hook.py output changes, compound-command accumulation, per-tool
resolution plumbing, `log_writer.py` audit-field extension, README documentation) is a
separate future plan, started only after both phases above are complete and reviewed.

## Verification

- `uv run python -m unittest discover -s test -t .` green after every increment and at
  the end of each phase.
- `uv run ruff check .` clean; `ruff format` on TOUCHED FILES ONLY, never repo-wide (see
  the Process section for why, and for the correction to the old "never format" rule).
- `uv run python tools/coverage_stdlib.py` at each phase end; no uncovered NEW lines in the
  touched modules without explicit justification.
- Manually load a config with a mixed plain-string + structured-entry
  `toolguard_hook.toml` (via a throwaway test fixture file) and confirm: (a) all patterns
  match correctly, (b) `/sort-permissions` round-trips it without corrupting the
  structured entry, (c) a deliberately malformed structured entry produces a logged
  validation warning/error rather than vanishing silently, (d) a structured entry placed in
  a native `settings.json` layer is rejected/ignored as structured (native-only-plain-string
  restriction), with a logged warning rather than being silently interpreted.
- **Added in revision 2, the two defect-specific manual checks:** (e) run a real
  `toolguard-migrate` against a config holding a structured entry plus a divergent native
  pattern -- the structured entry must still be there, byte-identical, afterwards (defect
  W1); (f) run a real maintenance rule-apply against a file holding a structured entry --
  it must not raise, and must not touch the entry (defect W2). Both in a throwaway
  directory, never against Arnon's live config.
- Same two checks against a `toolguard_hook.json` config (JSON path).

## Additional small fix folded into this ticket (2026-07-24, unrelated to structured entries)

Found while dogfooding: `_rules_dir()` (`config.py`, TOO-30) only resolves to
`$XDG_CONFIG_HOME/toolguard/rules` (default `~/.config/toolguard/rules`) -- it never scans
`~/.toolguard/rules/`, a separate pre-existing directory (backups/traces/stage/
install-journal) that looks similar enough that a real rules file (`gh.rules.toml`, a
substantial hand-crafted gh CLI ruleset) ended up there and was silently never enforced.
Workaround applied immediately: symlinked the file into the real discovery path. Arnon
declined a separate ticket for the real fix ("small fix we can make in the current
ticket") -- folded into TOO-19 instead of filed standalone. See
[[project_toolguard_rules_dir_missing_scan_target]] for the full incident.

**Fix shape (not yet implemented, sketch only):** `_rules_dir()` should return multiple
candidate directories (e.g. rename to `_rules_dirs() -> Tuple[Path, ...]`), scanning both
the XDG path and `~/.toolguard/rules/`; update `_discover_rules_files`/
`_group_rules_files_by_stem` call sites in `load_configuration()` to iterate both. Open
design question, now SETTLED: precedence when the SAME stem exists in
both directories -- **XDG path wins**, mirroring the existing TOML-over-JSON precedence
pattern already in `_group_rules_files_by_stem`. Confirmed by Arnon at the revision-2
review. Treat both directories as the same specificity level (both are user-scope), not
two separate hierarchy levels.

**Scheduling (revision 2):** this is Phase 0a **increment 0** -- done FIRST, before any
`RuleEntry` work. It is genuinely independent (Arnon folded it into TOO-19 only because it
is too small to justify its own ticket, not because it is related), and doing it first
lets the `gh.rules.toml` symlink workaround be retired early rather than lingering to the
end of the ticket.

Where this lands: independent of the `RuleEntry`/structured-entry work above -- can be
done as its own small increment, in either phase or even before Phase 0a starts, since it
has no dependency on anything else in this plan.

## Related bug found while verifying the above (2026-07-24): `_level_for_path` mislabels the symlinked file

Confirmed Arnon's suspicion after he noticed the verification output labeled the
symlinked `gh.rules.toml` as `"project"` instead of `"user"`. Root cause traced precisely:
`_level_for_path()` (`config.py:1853`) checks whether `path.resolve()` falls under
`~/.claude` or under `_rules_dir()` (the XDG path); `Path.resolve()` follows symlinks to
their real target, so the symlinked file's resolved path (the real
`~/.toolguard/rules/gh.rules.toml`) matches neither anchor and falls through to the
`"project"` default.

**Severity: cosmetic/reporting only, not a resolution bug.** The numeric `specificity`
(what actually drives more-specific-wins precedence) is set independently in
`_discover_levels` and is already correct (user-level tier). Only the human-readable
`level` string is wrong -- but that still matters for anything that surfaces it (audit/
maintenance reports, reason-string provenance suffixes).

**Resolution (Arnon, KISS):** don't build special symlink-resolution handling -- just add
the new `~/.toolguard/rules/` scan directory as a THIRD recognized anchor in
`_level_for_path`'s anchor tuple, alongside `~/.claude` and `_rules_dir()`. Both
directories are equally valid user-level locations. This single change closes both this
labeling bug (once the file lives there, symlinked or not, its resolved path falls under
a recognized anchor) and the missing-scan-target bug in the same section above --
implement together, same anchor-tuple edit plus the actual directory-scanning change.

## TOO-19 completion gate: remove the symlink workaround

**Before closing TOO-19, remind Arnon to remove the symlink**
`~/.config/toolguard/rules/gh.rules.toml -> ~/.toolguard/rules/gh.rules.toml` (created
2026-07-24 as an immediate workaround). Once the "scan ~/.toolguard/rules/ too" fix above
lands, the symlink becomes redundant -- `gh.rules.toml` will be discovered natively from
its real location. Leaving the symlink in place afterward is harmless but pointless
clutter; clean it up as part of wrapping up this ticket.