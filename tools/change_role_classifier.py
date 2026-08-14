#!/usr/bin/env python
"""
Dev-only measurement instrument, not shipped (the wheel's ``packages`` list is
``["toolguard"]``). Built for the TOO-45 architecture experiment: implement the
same small requirement in two candidate codebases and ask which one absorbed it
better.

Counting changed FILES measures the size of the requirement, not the quality of
the code that received it. This tool measures something sharper: for every place
a "subject" identifier (a field/config-key/flag introduced or changed by the
requirement) is touched, what ROLE does it play there?

- DECISION -- the subject participates in a branch, comparison, boolean operation,
  predicate, match statement, or conditional-expression test. This is where the
  requirement's actual logic lives.
- WRITE -- the subject is an assignment target, is mutated, or is serialised /
  persisted out (an attribute or mapping write).
- CONDUIT -- the subject appears only in transport position: argument, return
  value, forwarded into a call, iterated over, used to build a container that is
  itself just forwarded. It moves but nothing is decided by it.
- CEREMONY -- import statements, function-signature parameters (the declaration
  itself, not later uses of it), type annotations, and scope declarations
  (``global``/``nonlocal``).

One occurrence can carry more than one role, and every role found is reported.
Where a single label is needed the precedence is
DECISION > WRITE > CONDUIT > CEREMONY.

Role labels are per-location annotation, never a score
--------------------------------------------------------
Do not recombine them into a comparative number, and in particular do not restore
the CONDUIT-to-DECISION ratio this tool used to publish. An adversarial review
retired that ratio as the wrong measure rather than a buggy one: a mechanical,
architecture-neutral edit (``sed 's/entry\\.subject)/entry.subject or None)/g'``)
moved a tree from the worst possible reading to the best, and even with every
role-classification defect fixed, a trivial short-circuit default and a real
policy branch can score identically. What this tool stands behind is the
occurrence list -- matching verified exact against an independent AST oracle over
394 occurrences -- and the symbol closure listing.

Symbol closure: the subject is a NAME, not a value
------------------------------------------------------
A well-factored codebase routes a value through a module-level constant and a
small accessor, so matching the subject's literal spelling alone goes blindest
exactly where the code is cleanest. :func:`compute_symbol_closure` grows a bounded
set of additional tracked names by DEFINITION-SITE analysis only, never name
similarity: a name assigned the subject string, a name assigned from an
already-tracked name, or a function whose return/yield expression mentions an
already-tracked name. ``--closure-hops`` (default 2) bounds the growth; both the
members and the candidates cut off by the limit are listed.

Opaque hops: measuring what closure cannot follow
------------------------------------------------------
Closure cannot trace a tracked symbol's value through an ordinary function-local
variable (``value = self.metadata.get(THE_KEY); return value is True`` -- the
final comparison is invisible). Rather than solving intra-procedural dataflow,
the tool COUNTS these crossings (:func:`_find_opaque_hops_in_scope`), split
production/test, printed next to the role breakdown: an asymmetry between two
trees' opaque-hop counts means their DECISION counts are not a fair comparison
even when the role counts read identically.

Stdlib only, like toolguard's own runtime.

Never match on name substrings
-------------------------------
Resolution is exact identifier equality on ``ast`` node fields, so a subject named
``mode`` never matches ``auto_mode`` or ``mode_string``. This is a hard
requirement rather than an implementation detail: an earlier instrument on this
same ticket substring-matched, and both over- and under-counted as a result.

Scope-aware alias tracking (single hop, per scope, branch-insensitive)
------------------------------------------------------------------------
A subject that flows through an intermediate local variable before reaching a
branch is still attributed to the subject: ``tmp = subject`` is classified at the
assignment (CONDUIT -- the hop), and every later ``tmp`` use within the *same*
scope is classified by ITS OWN context and tagged ``via_alias``, so ``if tmp:``
becomes DECISION. This is a fixed-point closure over direct ``name = name``
assignments, computed per lexical scope (module / function / class body,
including nested control-flow blocks but NOT nested function/class/lambda
bodies), and is deliberately NOT flow- or branch-sensitive -- see
:data:`KNOWN_LIMITATIONS`.

Parse failures and unrecognised constructs
--------------------------------------------
A file that fails to parse is named in ``parse_failures`` and excluded from the
counts rather than folded into a zero. An AST construct this tool has no rule for
produces an explicit UNCLASSIFIED occurrence, counted and printed separately.
:data:`KNOWN_LIMITATIONS` lists what the tool structurally cannot see at all
(``getattr``/``**kwargs`` reach, runtime dispatch, a decision expressed by
choosing between call sites, a subject renamed between two trees).

Test vs. production, by path
-------------------------------
Decided by :func:`is_test_path`. The two tree modes additionally apply
:func:`_root_forces_test_context`, for a root that is itself inside a test-like
directory; git-diff mode has no such root and does not. The full file lists behind
the split are always printed, not just counts, so a misfiled tree is visible at a
glance.

Three input modes
--------------------
``--tree DIR``
    Single source tree. EVERY occurrence of the subject anywhere in the tree
    counts as a "changed location" -- correct for a freshly-introduced identifier,
    where there is no prior state to diff against.

``--old DIR --new DIR``
    Two source trees of the SAME codebase. Restricts analysis to lines that
    differ (added or replaced) in the NEW tree, computed per-file via
    :mod:`difflib` against the CHANGED STATEMENT's full line span rather than the
    occurrence's own line (see :func:`_enclosing_statement_span`). An OLD path with
    no NEW counterpart is reported as removed unless its content matches a new path,
    in which case it is treated as a move and diffed against it.

``--repo DIR --base REV --head REV``
    Git-diff mode. ``git diff --name-status -M`` finds the changed ``*.py`` files
    and resolves a renamed file's pre-image from its OLD path; ``git show`` reads
    the content, decoded via :func:`_decode_python_bytes`. The same
    statement-span changed-line restriction as ``--old``/``--new`` then applies.

Usage::

    uv run python tools/change_role_classifier.py --tree /path/to/tree --subject allow_in_auto_mode
    uv run python tools/change_role_classifier.py --old OLD --new NEW --subject some_field --json
    uv run python tools/change_role_classifier.py --repo . --base HEAD~5 --head HEAD --subject some_field
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import difflib
import io
import json
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path
from typing import Sequence

# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------

ROLE_DECISION = "DECISION"
ROLE_WRITE = "WRITE"
ROLE_CONDUIT = "CONDUIT"
ROLE_CEREMONY = "CEREMONY"
ROLE_UNCLASSIFIED = "UNCLASSIFIED"  # honesty bucket, not one of the four real roles

_ROLE_PRECEDENCE = (
    ROLE_DECISION,
    ROLE_WRITE,
    ROLE_CONDUIT,
    ROLE_CEREMONY,
    ROLE_UNCLASSIFIED,
)


def _role_sort_key(role: str) -> int:
    return _ROLE_PRECEDENCE.index(role)


def primary_role(roles: Sequence[str]) -> str:
    """Single-label reduction using the DECISION > WRITE > CONDUIT > CEREMONY precedence
    (UNCLASSIFIED only wins if nothing else matched)."""
    return min(roles, key=_role_sort_key)


MAX_WALK_DEPTH = 60
DEFAULT_CLOSURE_HOP_LIMIT = 2

KNOWN_LIMITATIONS = [
    'Values reached only through `getattr(obj, "name")`, `**kwargs`, or a dict lookup by '
    'string key (e.g. `config["subject_name"]`) are invisible to identifier-based AST '
    "matching -- the subject there is a string constant, not a Name/Attribute node. Exact "
    "string-literal matches on the subject text ARE surfaced separately as "
    "'string literal mentions' (not classified into a role) so they are visible rather than "
    "silently absent -- but this is a lower bound, not a role "
    "classification, and does not attempt substring or fuzzy matching of string contents.",
    "Roles that only exist through runtime dynamic dispatch (a decision made by which "
    "subclass's method gets called, a plugin registry keyed by the subject's value, "
    "monkeypatching) are invisible -- this is a static AST tool with no type inference and "
    "no control-flow graph.",
    "A decision expressed by choosing between two call sites or two code paths at a higher "
    'level ("call handler_a() vs handler_b() depending on config") rather than by a visible '
    "comparison/branch on the subject itself is invisible here -- this tool only sees the "
    "subject's OWN syntactic context, not decisions made about it elsewhere.",
    "A subject renamed between two trees (e.g. `allow_in_auto_mode` in tree A vs "
    '`auto_mode_allowed` in tree B) is not detected as "the same concept" -- each tree must '
    "be analyzed with the subject spelling that tree actually uses; this tool does not infer "
    "renames.",
    "Alias tracking is a single-hop-per-name, branch-insensitive, per-scope fixed-point over "
    "direct `plain_name = subject` assignments only. It does not track destructuring "
    "assignment (`a, b = subject, other`), does not follow the subject through a function "
    "call and back, does not cross function boundaries, and does not account for "
    "reassignment inside a loop or conditional (a later unconditional reassignment to an "
    "unrelated value is not detected, so a stale alias can be over-attributed).",
    "Two occurrences of the same spelling in genuinely unrelated scopes (a coincidentally "
    "same-named local variable in an unrelated function) are NOT filtered out -- this tool "
    "has no way to know, from syntax alone, that they are unrelated to the requirement's "
    "subject. Both are reported. Scope IS used to keep alias tracking correctly bounded (an "
    "alias in one function is never treated as related to a same-named alias in another), "
    "but the base subject match itself is deliberately inclusive: silently excluding a "
    "same-named site because it 'looks unrelated' is exactly the kind of guess this tool "
    "refuses to make.",
    "Comprehension and generator-expression bodies are not treated as separate lexical "
    "scopes for alias-hop tracking (a simplification; role classification of decisions/"
    "writes/conduits WITHIN a comprehension is still correct, only the alias-hop feature "
    "treats the comprehension as part of its enclosing scope).",
    f"A walk that cannot find a recognised governing construct within {MAX_WALK_DEPTH} parent "
    "levels, or that reaches an AST parent/field combination with no rule in this tool, is "
    "reported as UNCLASSIFIED rather than guessed -- never folded into any of the four real "
    "roles and never silently dropped from the totals.",
    "A `def`/`class` whose OWN NAME equals the subject (e.g. a `@property def "
    "subject_name(self):`) is caught as a WRITE at its definition site. As of the second "
    "closure-growth revision (CLOSURE_RULE_RETURNS_TRACKED, widened after adversarial review: "
    "see its own module-level comment for the two prior, replaced versions), a function whose "
    "return expression references a tracked symbol ANYWHERE within it -- including "
    "`return self.metadata.get(THE_KEY)`, a one-line accessor through a lookup -- now correctly "
    "joins the closure itself, not merely making `THE_KEY` visible as a separate occurrence. "
    "What is STILL invisible: once the lookup result is assigned to a fresh LOCAL variable and "
    "THAT local, not the tracked symbol itself, is what a LATER return statement compares or "
    "branches on (`value = self.metadata.get(THE_KEY); return value is True` -- the SECOND "
    "statement's return expression contains only `value`, not `THE_KEY`), the function still "
    "does not join via this rule, and the final comparison is not directly attributed to "
    "anything by closure growth -- measured separately by the OPAQUE HOP count instead (see "
    "the tool's own printed output; `_find_opaque_hops_in_scope` was fixed in the same round "
    "to actually detect this shape, having previously only inspected assignments). This is "
    "exactly what remains true of `RuleEntry.allow_in_auto_mode` on both TOO-45 validation "
    "trees: the `.get(ALLOW_IN_AUTO_MODE_KEY)` call and the property itself are both found "
    "(the property via its own name, the call via `ALLOW_IN_AUTO_MODE_KEY`'s own tracked "
    "occurrence), but the `value is True` comparison one line later is only visible as an "
    "opaque hop, not a closure member.",
    "SYMBOL CLOSURE cannot follow: dynamic dispatch (a decision made by which subclass's "
    "method runs); `getattr(obj, computed_name)` where `computed_name` is itself computed at "
    "runtime rather than a literal or a tracked constant; a value that crosses a serialisation "
    "boundary and comes back (written to JSON/TOML under the subject's key, then read back "
    "elsewhere as a freshly-parsed dict with no static link to the writing code); and any "
    f"constant/reader-function relationship that needs more than `--closure-hops` (default "
    f"{DEFAULT_CLOSURE_HOP_LIMIT}) hops to reach -- reported explicitly in 'excluded by hop "
    "limit', never silently dropped, but the excluded-by-hop-limit report itself only probes "
    "exactly one hop past the limit (see the walk-depth entry above for the analogous "
    "bounded-probe caveat elsewhere in this tool).",
    "Closure growth via CLOSURE_RULE_RETURNS_TRACKED requires a tracked symbol to appear "
    "SOMEWHERE within a return (or yield/yield-from) VALUE EXPRESSION -- `return bool(TRACKED)`, "
    "`return TRACKED or default`, `return TRACKED if TRACKED else other`, "
    "`return metadata.get(TRACKED)`, and a delegating wrapper (`return accessor()`, chained "
    "through the normal hop mechanism) all count, found by walking the return expression's "
    "full subtree rather than requiring it to BE a bare Name/Attribute. This is deliberately "
    "wide: earlier this round the rule required an exact bare match, which tested the AUTHOR'S "
    "PUNCTUATION rather than whether the function carries the value -- adversarially found "
    "(second review, N1): `return A and B and entry.subject and C` was rejected while a "
    "semantically-identical `if not A: return False` / `return entry.subject` was accepted, so "
    "a purely stylistic three-line rewrite of one predicate body moved a real tree's reported "
    "occurrences from 5 to 11 with no architectural change at all. What is STILL excluded, "
    "correctly: a function whose return value expression does NOT itself mention the tracked "
    "symbol, even if an EARLIER statement in the same function does (`has_key = TRACKED in "
    "metadata; ...; return build_issue_list(metadata)` -- `TRACKED` never appears in the "
    "returned expression) -- this is what stops the original, much larger explosion (`command` "
    "growing to a 19-name closure including `main`/`run_maintenance`, 58% false-positive "
    "occurrences). The locally-bound-name exclusion (stop a same-spelled parameter -- "
    "`def unrelated(subject_name): return subject_name` -- from falsely pulling an unrelated "
    "function into the closure) still applies the same way, with the same conservative "
    "over-exclusion trade-off as before. Implicit returns are covered where reasonably "
    "possible (`yield`/`yield from` inside a generator are scanned identically to `return`); "
    "a value computed once and cached on an instance attribute in `__init__` and later "
    "returned bare by a separate property (`self._cache = self.metadata.get(THE_KEY)` in "
    "`__init__`, then `return self._cache` in a property) is NOT covered -- the cached "
    "attribute's OWN assignment is not itself a return/yield, so tracing it would require "
    "following an assignment across two different methods of the same class, which was judged "
    "out of scope for this round.",
    "Closure-growth constant/alias scanning is restricted to module-level and class-level "
    "simple assignments (`NAME = <expr>` or `NAME: T = <expr>`, single plain-Name target) -- "
    "it does not look inside function bodies for new constant-like bindings (the existing, "
    "separate per-occurrence local alias-hop feature already covers function-local aliasing "
    "for a single occurrence's own classification, but it does not feed new names into the "
    "closure the way a module-level constant does).",
    "No CONDUIT-to-DECISION ratio is published (retired after an independent adversarial "
    "review, not merely patched): `sed 's/entry\\.subject)/entry.subject or None)/g'` moved a "
    "tree from the worst possible reading to the best with no architectural change (`X or "
    "None` puts the subject in an unconditional-DECISION `BoolOp`), and wrapping every `if "
    "entry.subject:` in `bool(...)` pulled the same lever backwards. Even with the Call/"
    "Attribute walk-through defect (below) fixed, a trivial short-circuit default and a real "
    "policy branch can still score identically -- this is not a bug in the walk, it is the "
    "measure being the wrong one for 'did the refactor pay off'. Role labels remain as "
    "descriptive per-location annotation; they are never recombined into a single number. "
    "Relatedly, `BoolOp` (`X or Y`) is STILL an unconditional terminal DECISION regardless of "
    "whether its result is actually branch-tested or merely used for defaulting -- the fix "
    "considered (gate it on whether the walk eventually reaches a genuine branch-test "
    "construct, exactly like the Call/Attribute fix below) was deliberately NOT applied, "
    "because retiring the ratio removes the mechanism that made this gameable (a single "
    "location's label is low-stakes; a headline number built by summing it was not) and "
    "applying the same walk-through treatment carries its own regression risk that was not "
    "validated here. A `X or None` default therefore still LABELS as DECISION at that "
    "location, which is imprecise but, without a ratio to feed, no longer load-bearing.",
    "`_governing_role`'s Call/Attribute/keyword/NamedExpr walk-through fix (dual CONDUIT+"
    "DECISION role) was applied to exactly the constructs the first adversarial review found "
    "broken (`Call.args`/`Call.func`, `Attribute.value`, `keyword.value`, `NamedExpr.value`) "
    "plus nothing else. The second review found one gap in that set that had NOT actually been "
    "fixed: `keyword.value`'s own hop correctly continued the walk, but its parent `Call` node "
    '(field `"keywords"`, a SEPARATE field from `"args"`) had no rule, so `if f(key=subject):` '
    "still terminated at bare CONDUIT with an unhandled-construct note nobody printed (N5) -- "
    'now fixed by adding `"keywords"` alongside `"args"`/`"func"`. Deliberately still NOT '
    "extended further: `Subscript`, `For.iter`, `withitem.context_expr`, `Raise`, `Lambda.body`, "
    "`Return.value`, `Yield`/`YieldFrom.value` and `FormattedValue.value` remain terminal "
    "CONDUIT, so `if data[subject]:` or `if (yield subject):` can still terminate at CONDUIT "
    "before reaching an enclosing branch test -- the SAME class of defect, left unfixed because "
    "role-label precision beyond the specific gaps already found is now explicitly "
    "deprioritised (mechanical scoring was abandoned; role labels are descriptive annotation on "
    "an evidence list, not inputs to a computed comparison), and going further would risk an "
    "unverified change for a benefit that no longer feeds any computed number.",
    "SYMBOL CLOSURE over-attribution, found adversarially (F7, first review) and "
    "DELIBERATELY NOT fixed (disproportionate; concrete examples so the gap is auditable, not "
    "silent): (1) REBINDING is not noticed -- `KEY = 'subject'` followed later by "
    "`KEY = 'something_unrelated'` leaves `KEY` tracked for the rest of the file, so every "
    "later read of `KEY` (now bound to a different string entirely) is still credited to the "
    "subject. COMPOUNDS as of the second review's widened return-expression rule (N10): "
    "`def use(d): return KEY` now joins the closure off the REBOUND (unrelated) constant too, "
    "growing the phantom set rather than leaving it fixed in place. (2) A SAME-NAMED but "
    "semantically unrelated constant in a different module is credited: `MODE = 'subject'` in "
    "one file and an unrelated `class Unrelated: MODE = 'other'` with `if self.MODE == 'x':` "
    "in a different file can produce a phantom occurrence attributed to the subject, because "
    "closure growth has no cross-module identity check beyond the exact string match at the "
    "point each constant is DEFINED. (3) ALIASED IMPORTS are not followed inward -- "
    "`from pkg.a import real_thing as subject` tracks the local name `subject` but never "
    "`real_thing`, so the defining module's OWN uses of `real_thing` are invisible. All three "
    "would require either runtime-order-sensitive reasoning (1), cross-module value identity "
    "beyond string equality (2), or import-alias resolution back to the defining symbol (3) -- "
    "each is a reasonable next step, none was attempted.",
    "Test/production classification is a path heuristic and has ONE known, undecidable-by-"
    "filename-alone blind spot in each direction, both deferred: a file genuinely named "
    "`test_helpers.py` that is itself shared PRODUCTION support code (not a test module) "
    "cannot be told apart from a genuine test module by filename alone (F6, first review) -- "
    "resolving it would mean guessing intent, which this tool refuses to do; the full "
    "TEST/PRODUCTION file lists are always printed so a misfiled tree is at least visible, not "
    "silently wrong. Separately, `_root_forces_test_context` (which treats every file under "
    "the analysis root as test when the root itself sits inside a test-like directory) is "
    "bounded to the root's trailing few path components (N7, second review: the unbounded "
    "version inspected the ENTIRE absolute ancestor chain, so a throwaway tree's arbitrary "
    "parent directory -- e.g. a machine's home directory happening to be under a path "
    "containing 'test' -- could silently zero out an entire tree's production bucket; bounding "
    "fixes that case). The bound does NOT and structurally CANNOT resolve the adversary's own "
    "worst-case example, `.../spec/candidateA/`, where `spec` is the immediate parent of the "
    "analysis root: that is PATH-SHAPE-IDENTICAL to the legitimate case this mechanism exists "
    "to catch (`--tree path/to/test/unit`, where `test` is also the immediate parent) -- no "
    "path heuristic can tell 'spec is a real test-framework directory' apart from 'spec "
    "happens to be this scratch tree's parent for an unrelated reason' without semantic "
    "understanding neither version of this check has. The file-list backstop above is the "
    "mitigation for this specific, irreducible case too.",
    "Two deferred, lower-severity findings from the second adversarial review, each with a "
    "concrete reproduction: (N6) `_enclosing_statement_span` (the diff-mode line-filtering "
    "fix) returns the SMALLEST enclosing statement, which for a function/class declaration IS "
    "the entire function/class body -- so changing an unrelated line deep inside a function "
    "named `subject` (or with a parameter named `subject`) books that function's OWN NAME/"
    "parameter as a changed occurrence in diff mode, inflating CEREMONY/WRITE in proportion to "
    "how large the enclosing body is; the mirror image of the defect this mechanism was built "
    "to fix. (N8) `CLOSURE_RULE_OWN_NAME` is effectively unreachable as written -- `consider()` "
    "returns early for any name already in the seed subject set, and this rule only ever fires "
    "for names IN that set, so it can never actually add anything (the seed dict already "
    "covers whatever it would have added). Harmless in practice (nothing is lost), but the "
    "rule is advertised in code comments as one of three active growth rules and will never "
    "appear in a closure listing as the admitting rule; not fixed or removed this round.",
    "A `.py` file reachable through two different relative paths (a file-level symlink, as "
    "opposed to the now-traversed symlinked DIRECTORY case) is parsed and counted twice -- "
    "confirmed unchanged from the first adversarial review (F9/N11) and not addressed this "
    "round; both occurrences are individually correct, but the same underlying code is "
    "double-counted across the two paths.",
]

# --------------------------------------------------------------------------
# File discovery / test-vs-production
# --------------------------------------------------------------------------

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".pyscn",
    "build",
    "dist",
    "cover",
}


def discover_python_files(root: Path) -> list[Path]:
    """Every ``*.py`` file under *root*, as paths relative to *root*, skipping build/VCS/cache
    noise directories. Sorted for deterministic output.

    ``recurse_symlinks=True`` because ``Path.rglob`` defaults it to False: a ``*.py`` file
    reachable only through a symlinked package directory is otherwise absent from
    ``files_analyzed``, ``production_files``/``test_files`` and ``parse_failures`` alike,
    because discovery never yields the path at all. Nothing here deduplicates, so a directory
    symlink that loops back into the tree makes one file discoverable under many paths."""
    found: list[Path] = []
    for path in root.rglob("*.py", recurse_symlinks=True):
        if any(
            part in EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts[:-1]
        ):
            continue
        found.append(path.relative_to(root))
    return sorted(found)


TEST_DIR_NAMES = frozenset({"test", "tests", "spec", "specs"})
TEST_INFRA_FILENAMES = frozenset({"conftest.py"})


def is_test_path(relpath: Path) -> bool:
    """True if *relpath* is TEST code: any directory component is exactly one of
    :data:`TEST_DIR_NAMES`, the filename is in :data:`TEST_INFRA_FILENAMES`, or the filename
    matches `test_*.py`/`*_test.py`. Everything else is production.

    A path heuristic, not semantic analysis, with an irreducible blind spot in one direction:
    a file genuinely named `test_helpers.py` that is itself shared PRODUCTION support code
    cannot be told apart from a real test module by filename alone. Resolving that would mean
    guessing intent, so the per-file classification is printed in full instead."""
    if any(part in TEST_DIR_NAMES for part in relpath.parts[:-1]):
        return True
    name = relpath.name
    if name in TEST_INFRA_FILENAMES:
        return True
    return name.startswith("test_") or name.endswith("_test.py")


#: How many of *root*'s own TRAILING path components :func:`_root_forces_test_context`
#: inspects. Bounded deliberately: checking the whole absolute ancestor chain lets any
#: unrelated ancestor named "test"/"spec" -- a home directory, a scratch-space convention,
#: anything upstream that has nothing to do with the tree's content -- classify the entire
#: tree as test code and empty its production bucket. A small trailing window still catches
#: the intended case, ``--tree path/to/test/unit``.
_ROOT_TEST_CONTEXT_WINDOW = 4


def _root_forces_test_context(root: Path) -> bool:
    """True if *root* itself -- the tree or subtree the tool was pointed AT -- sits inside a
    test-like directory within its last :data:`_ROOT_TEST_CONTEXT_WINDOW` path components
    (e.g. ``--tree path/to/test/unit``). Relative-path classification cannot see this, because
    that 'test' component was consumed by being the analysis ROOT rather than appearing in any
    reported relative path. When true, every file under *root* is treated as test code
    regardless of its relative path."""
    parts = root.resolve().parts
    window = parts[-_ROOT_TEST_CONTEXT_WINDOW:] if parts else parts
    return any(part in TEST_DIR_NAMES for part in window)


TEST_VS_PRODUCTION_RULE = (
    "a path is TEST code if any directory component is exactly 'test'/'tests'/'spec'/'specs', "
    "the filename is 'conftest.py', or the filename matches 'test_*.py'/'*_test.py'; "
    "everything else is production. If the analysis ROOT itself sits inside a test-like "
    "directory, every file under it is treated as test regardless of relative path. Full "
    "file lists behind this classification are printed below (never just counts)."
)

# --------------------------------------------------------------------------
# Occurrence records
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Occurrence:
    """One AST-node-identity match of a subject, with the role(s) it plays there."""

    file: str
    line: int
    col: int
    subject: str
    kind: str  # name | attribute | arg | def-name | import-alias | keyword-name |
    # except-name | match-as | match-star | match-mapping-rest | global | nonlocal
    roles: tuple[str, ...]
    via_alias: bool
    alias_chain: tuple[str, ...]
    notes: tuple[str, ...] = ()
    is_test: bool = False

    @property
    def primary_role(self) -> str:
        return primary_role(self.roles)


@dataclasses.dataclass(frozen=True)
class StringMention:
    """A string-literal constant whose value exactly equals a subject. Surfaced so a
    string-keyed use of the subject is at least visible; never classified into a role."""

    file: str
    line: int
    col: int
    subject: str
    is_test: bool = False


@dataclasses.dataclass(frozen=True)
class OpaqueHop:
    """A tracked symbol's value crosses into a fresh, untracked LOCAL name that is then used
    again -- e.g. ``value = self.metadata.get(THE_KEY); return value is True``. What happens
    to *local_name* past this point is intra-procedural dataflow, out of scope by design, so
    each of these is a place a DECISION could be hiding, uncounted. Measured, not classified;
    :func:`_find_opaque_hops_in_scope` has the exact rule."""

    file: str
    line: int
    col: int
    local_name: str
    tracked_symbols_involved: tuple[str, ...]
    is_test: bool = False


@dataclasses.dataclass
class FileAnalysis:
    file: str
    parse_error: str | None
    occurrences: list[Occurrence]
    string_mentions: list[StringMention]
    opaque_hops: list[OpaqueHop] = dataclasses.field(default_factory=list)
    #: Set whether or not anything matched, so the per-bucket file lists can name files with
    #: zero occurrences too.
    is_test: bool = False


# --------------------------------------------------------------------------
# AST indexing (one traversal builds parent map, scope map, and candidate lists)
# --------------------------------------------------------------------------


@dataclasses.dataclass
class _TreeIndex:
    parent_map: dict[int, tuple[ast.AST, str, int | None]] = dataclasses.field(
        default_factory=dict
    )
    scope_of: dict[int, ast.AST] = dataclasses.field(default_factory=dict)
    name_nodes: list[ast.Name] = dataclasses.field(default_factory=list)
    attribute_nodes: list[ast.Attribute] = dataclasses.field(default_factory=list)
    arg_nodes: list[ast.arg] = dataclasses.field(default_factory=list)
    alias_nodes: list[ast.alias] = dataclasses.field(default_factory=list)
    keyword_nodes: list[ast.keyword] = dataclasses.field(default_factory=list)
    except_handlers: list[ast.ExceptHandler] = dataclasses.field(default_factory=list)
    match_as_nodes: list[ast.MatchAs] = dataclasses.field(default_factory=list)
    match_star_nodes: list[ast.MatchStar] = dataclasses.field(default_factory=list)
    match_mapping_nodes: list[ast.MatchMapping] = dataclasses.field(
        default_factory=list
    )
    global_nodes: list[ast.Global] = dataclasses.field(default_factory=list)
    nonlocal_nodes: list[ast.Nonlocal] = dataclasses.field(default_factory=list)
    string_constants: list[ast.Constant] = dataclasses.field(default_factory=list)
    scope_nodes: list[ast.AST] = dataclasses.field(default_factory=list)
    def_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = (
        dataclasses.field(default_factory=list)
    )


_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _build_index(tree: ast.Module) -> _TreeIndex:
    idx = _TreeIndex()
    idx.scope_nodes.append(tree)

    def walk(
        node: ast.AST,
        current_scope: ast.AST,
        parent: ast.AST | None,
        field: str | None,
        index: int | None,
    ) -> None:
        if parent is not None:
            idx.parent_map[id(node)] = (parent, field, index)
        idx.scope_of[id(node)] = current_scope
        next_scope = current_scope
        if isinstance(node, _SCOPE_TYPES) and node is not tree:
            next_scope = node
            idx.scope_nodes.append(node)

        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                idx.def_nodes.append(node)
            case ast.Name():
                idx.name_nodes.append(node)
            case ast.Attribute():
                idx.attribute_nodes.append(node)
            case ast.arg():
                idx.arg_nodes.append(node)
            case ast.alias():
                idx.alias_nodes.append(node)
            case ast.keyword():
                idx.keyword_nodes.append(node)
            case ast.ExceptHandler():
                idx.except_handlers.append(node)
            case ast.MatchAs():
                idx.match_as_nodes.append(node)
            case ast.MatchStar():
                idx.match_star_nodes.append(node)
            case ast.MatchMapping():
                idx.match_mapping_nodes.append(node)
            case ast.Global():
                idx.global_nodes.append(node)
            case ast.Nonlocal():
                idx.nonlocal_nodes.append(node)
            case ast.Constant(value=str()):
                idx.string_constants.append(node)

        for fname, value in ast.iter_fields(node):
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        walk(item, next_scope, node, fname, i)
            elif isinstance(value, ast.AST):
                walk(value, next_scope, node, fname, None)

    walk(tree, tree, None, None, None)
    return idx


# --------------------------------------------------------------------------
# Role classification
# --------------------------------------------------------------------------

_TRANSPARENT = object()  # keep walking up; this construct doesn't decide the role
_CONTINUE = object()  # like _TRANSPARENT, but the caller must also record a role


def _direct_role_for_ctx(node: ast.AST) -> frozenset[str] | None:
    """WRITE for a Store or Del context -- Python's own ``.ctx`` already says whether an
    occurrence is a binding target or a deletion, so no target detection is hand-rolled here.
    None for a Load context (or no ctx at all), meaning the caller must walk up to find the
    governing construct."""
    ctx = getattr(node, "ctx", None)
    if isinstance(ctx, (ast.Store, ast.Del)):
        return frozenset({ROLE_WRITE})
    return None


def _write_or_conduit_for_targets(targets: list[ast.expr]) -> frozenset[str]:
    """Role for the RHS ``value`` of an Assign/AnnAssign/AugAssign: WRITE if any target
    persists into an object or mapping (Attribute/Subscript), CONDUIT if every target is a
    plain local Name -- the value merely flows into a local, whose own alias hop is registered
    separately in :func:`_compute_aliases`. Tuple/List destructuring counts as CONDUIT, with
    the alias-hop limitation documented in :data:`KNOWN_LIMITATIONS`."""
    if any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in targets):
        return frozenset({ROLE_WRITE})
    return frozenset({ROLE_CONDUIT})


def _governing_role(parent: ast.AST, field: str) -> frozenset[str] | object | None:
    """Classifies a Load-context occurrence by the nearest ancestor that actually determines a
    role. Returns a frozenset of roles (terminal -- stop walking), ``_TRANSPARENT`` (this
    construct doesn't decide anything itself, keep walking up from *parent*), a
    ``(_CONTINUE, frozenset[str])`` pair (this construct DOES tag a real role -- e.g. CONDUIT
    for a call argument -- but is not itself the last word: keep walking to see whether a MORE
    governing construct exists further up, and report BOTH roles if so), or ``None`` (no rule
    recognises this parent/field combination -- the caller reports UNCLASSIFIED rather than
    dropping it).

    ``_CONTINUE`` earns its complexity. With a terminal CONDUIT here, `if bool(x):`,
    `if x.enabled:`, `if x.is_ready():` and `if (found := x) is not None:` all stop at the
    call/attribute/walrus before ever reaching the enclosing `If.test`, so a decision
    expressed through one layer of indirection scores as pure transport -- which makes the
    tool prefer copy-pasted inline checks over factored predicates. The fix is a dual role,
    not a swap: the value genuinely DID move through the call (CONDUIT is still true) AND it
    genuinely IS the branch's own test (DECISION is also true)."""
    match parent:
        case ast.Compare() if field in ("left", "comparators"):
            return frozenset({ROLE_DECISION})
        case ast.BoolOp() if field == "values":
            return frozenset({ROLE_DECISION})
        case ast.UnaryOp() if field == "operand":
            return (
                frozenset({ROLE_DECISION})
                if isinstance(parent.op, ast.Not)
                else _TRANSPARENT
            )
        case ast.BinOp():
            return _TRANSPARENT
        case ast.If() if field == "test":
            return frozenset({ROLE_DECISION})
        case ast.While() if field == "test":
            return frozenset({ROLE_DECISION})
        case ast.IfExp() if field == "test":
            return frozenset({ROLE_DECISION})
        case ast.IfExp() if field in ("body", "orelse"):
            return _TRANSPARENT
        case ast.Assert() if field == "test":
            return frozenset({ROLE_DECISION})
        case ast.Assert() if field == "msg":
            return frozenset({ROLE_CONDUIT})
        case ast.comprehension() if field == "ifs":
            return frozenset({ROLE_DECISION})
        case ast.comprehension() if field == "iter":
            return frozenset({ROLE_CONDUIT})
        case ast.Match() if field == "subject":
            return frozenset({ROLE_DECISION})
        case ast.match_case() if field == "guard":
            return frozenset({ROLE_DECISION})
        case ast.MatchValue() if field == "value":
            return frozenset({ROLE_DECISION})
        case ast.Assign() if field == "value":
            return _write_or_conduit_for_targets(parent.targets)
        case ast.AnnAssign() if field == "value":
            return _write_or_conduit_for_targets([parent.target])
        case ast.AugAssign() if field == "value":
            return _write_or_conduit_for_targets([parent.target])
        case ast.NamedExpr() if field == "value":
            return (_CONTINUE, frozenset({ROLE_CONDUIT}))
        case ast.Return() if field == "value":
            return frozenset({ROLE_CONDUIT})
        case ast.Yield() | ast.YieldFrom() if field == "value":
            return frozenset({ROLE_CONDUIT})
        case ast.Call() if field in ("args", "func", "keywords"):
            # "keywords" belongs here alongside "args": a `keyword.value` hop's own parent is
            # the enclosing `Call` at field "keywords", a separate field, so without it
            # `if f(key=subject):` walks keyword.value -> _CONTINUE -> unhandled construct and
            # terminates at bare CONDUIT.
            return (_CONTINUE, frozenset({ROLE_CONDUIT}))
        case ast.keyword() if field == "value":
            return (_CONTINUE, frozenset({ROLE_CONDUIT}))
        case ast.FormattedValue() if field == "value":
            return frozenset({ROLE_CONDUIT})
        case ast.Subscript() if field in ("slice", "value"):
            return frozenset({ROLE_CONDUIT})
        case ast.Attribute() if field == "value":
            return (_CONTINUE, frozenset({ROLE_CONDUIT}))
        case ast.For() | ast.AsyncFor() if field == "iter":
            return frozenset({ROLE_CONDUIT})
        case ast.withitem() if field == "context_expr":
            return frozenset({ROLE_CONDUIT})
        case ast.Raise() if field in ("exc", "cause"):
            return frozenset({ROLE_CONDUIT})
        case ast.Lambda() if field == "body":
            return frozenset({ROLE_CONDUIT})
        case ast.Dict() if field in ("keys", "values"):
            return _TRANSPARENT
        case ast.Set():
            # Unlike List/Tuple, a Set literal has NO `.ctx` field at all -- Python has no
            # set-destructuring assignment, so a set literal is only ever a value being built.
            # Folding it into the List/Tuple case below would test `.ctx` for None and send
            # every set-literal element to UNCLASSIFIED.
            return _TRANSPARENT
        case ast.List() | ast.Tuple() if isinstance(
            getattr(parent, "ctx", None), ast.Load
        ):
            return _TRANSPARENT
        case ast.Starred() if field == "value":
            return _TRANSPARENT
        case ast.ListComp() | ast.SetComp() | ast.GeneratorExp() if field == "elt":
            return _TRANSPARENT
        case ast.DictComp() if field in ("key", "value"):
            return _TRANSPARENT
        case _:
            return None


def _walk_up(node: ast.AST, idx: _TreeIndex) -> tuple[frozenset[str], tuple[str, ...]]:
    """Walks from a Load-context occurrence toward the root, through transparent wrappers and
    role-tagging-but-continuing hops (``_CONTINUE``), until a terminal governing construct is
    found. Roles recorded at ``_CONTINUE`` hops accumulate rather than being discarded, so an
    occurrence can end up with BOTH CONDUIT (it moved through a call/attribute) and DECISION
    (that call's result is what a branch tests). Never returns an empty role set: a construct
    with no rule, or a chain with no recorded parent, becomes UNCLASSIFIED with an explanatory
    note -- unless a real hop role was already accumulated, which is returned rather than
    discarded just because nothing further governs it."""
    current = node
    accumulated: set[str] = set()
    for _ in range(MAX_WALK_DEPTH):
        info = idx.parent_map.get(id(current))
        if info is None:
            if accumulated:
                return frozenset(accumulated), ()
            return frozenset({ROLE_UNCLASSIFIED}), (
                f"no recorded parent for {type(current).__name__} (top-level/unsupported context)",
            )
        parent, field, _index = info
        if field in ("annotation", "returns"):
            return frozenset({ROLE_CEREMONY}) | accumulated, (
                "reached via a type-annotation field",
            )
        result = _governing_role(parent, field)
        if result is _TRANSPARENT:
            current = parent
            continue
        if isinstance(result, tuple) and result[0] is _CONTINUE:
            accumulated |= result[1]
            current = parent
            continue
        if result is None:
            if accumulated:
                return frozenset(accumulated), (
                    f"reached unhandled construct {type(parent).__name__} (field={field!r}) "
                    "after at least one hop role was already recorded -- that role is kept, "
                    "not discarded",
                )
            return frozenset({ROLE_UNCLASSIFIED}), (
                f"unhandled construct {type(parent).__name__} (field={field!r})",
            )
        return frozenset(result) | accumulated, ()
    if accumulated:
        return frozenset(accumulated), (
            f"walk-up exceeded {MAX_WALK_DEPTH} levels after at least one hop role was recorded",
        )
    return frozenset({ROLE_UNCLASSIFIED}), (
        f"walk-up exceeded {MAX_WALK_DEPTH} levels",
    )


def _classify_ctx_node(
    node: ast.AST, idx: _TreeIndex
) -> tuple[frozenset[str], tuple[str, ...]]:
    """Classifies a single Name/Attribute occurrence: Store/Del is WRITE outright (with a dual
    role added for the walrus-in-a-test hazard -- `if (subject := f()):` is simultaneously a
    binding AND the very thing being tested); Load walks up via :func:`_walk_up`."""
    direct = _direct_role_for_ctx(node)
    if direct is not None:
        roles, notes = direct, ()
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            info = idx.parent_map.get(id(node))
            if info and isinstance(info[0], ast.NamedExpr) and info[1] == "target":
                extra_roles, extra_notes = _walk_up(info[0], idx)
                if ROLE_UNCLASSIFIED not in extra_roles:
                    roles = roles | extra_roles
                    notes = (
                        notes
                        + extra_notes
                        + ("walrus target also tested -- dual WRITE+DECISION role",)
                    )
        return roles, notes
    return _walk_up(node, idx)


# --------------------------------------------------------------------------
# Scope-local alias tracking (single hop, branch-insensitive, per scope)
# --------------------------------------------------------------------------


def _flatten_scope_statements(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """Flattens control-flow-block bodies (if/for/while/with/try/match) into one list so
    alias detection sees straight-line and branched assignments alike, WITHOUT descending into
    nested function/class/lambda bodies (those are separate scopes). This is a deliberate
    branch-insensitive approximation -- see :data:`KNOWN_LIMITATIONS`."""
    flat: list[ast.stmt] = []
    for stmt in stmts:
        flat.append(stmt)
        match stmt:
            case ast.If():
                flat.extend(_flatten_scope_statements(stmt.body))
                flat.extend(_flatten_scope_statements(stmt.orelse))
            case ast.For() | ast.AsyncFor():
                flat.extend(_flatten_scope_statements(stmt.body))
                flat.extend(_flatten_scope_statements(stmt.orelse))
            case ast.While():
                flat.extend(_flatten_scope_statements(stmt.body))
                flat.extend(_flatten_scope_statements(stmt.orelse))
            case ast.With() | ast.AsyncWith():
                flat.extend(_flatten_scope_statements(stmt.body))
            case ast.Try() | ast.TryStar():
                flat.extend(_flatten_scope_statements(stmt.body))
                for handler in stmt.handlers:
                    flat.extend(_flatten_scope_statements(handler.body))
                flat.extend(_flatten_scope_statements(stmt.orelse))
                flat.extend(_flatten_scope_statements(stmt.finalbody))
            case ast.Match():
                for case_ in stmt.cases:
                    flat.extend(_flatten_scope_statements(case_.body))
    return flat


def _compute_aliases(flat_stmts: list[ast.stmt], subjects: set[str]) -> dict[str, str]:
    """Fixed-point closure over direct `plain_name = subject_or_known_alias` assignments in a
    single scope's flattened statement list. Returns {alias_name: subject_name}."""
    aliases: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for stmt in flat_stmts:
            if not (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Name)
            ):
                continue
            target_name = stmt.targets[0].id
            source_name = stmt.value.id
            if target_name in subjects:
                continue  # never treat the subject's own name as "an alias of itself"
            origin = (
                source_name if source_name in subjects else aliases.get(source_name)
            )
            if origin is not None and aliases.get(target_name) != origin:
                aliases[target_name] = origin
                changed = True
    return aliases


def _scope_body_statements(scope_node: ast.AST) -> list[ast.stmt]:
    if isinstance(scope_node, ast.Lambda):
        return []  # a lambda body is a single expression; no assignments are possible
    return list(getattr(scope_node, "body", []))


def _tracked_refs_in_expr(expr: ast.expr, tracked_names: set[str]) -> tuple[str, ...]:
    """Every tracked name (Name.id or Attribute.attr) referenced anywhere within *expr* -- a
    full ``ast.walk``, not just the top-level node. This is the shared notion of "references"
    used by both closure growth's return/yield scan and opaque-hop detection."""
    return tuple(
        sorted(
            {
                n.id
                for n in ast.walk(expr)
                if isinstance(n, ast.Name) and n.id in tracked_names
            }
            | {
                n.attr
                for n in ast.walk(expr)
                if isinstance(n, ast.Attribute) and n.attr in tracked_names
            }
        )
    )


def _find_opaque_hops_in_scope(
    flat_stmts: list[ast.stmt], tracked_names: set[str], scope_is_tracked: bool = False
) -> list[tuple[ast.stmt, str, tuple[str, ...]]]:
    """Two independent sources of :class:`OpaqueHop`, both marking the same thing: a place a
    tracked symbol is genuinely involved but cannot be confidently attributed.

    1. An assignment to a plain local Name whose RHS mentions a tracked symbol inside a larger
       expression, where the local is then read again somewhere in this same flat scope --
       e.g. `value = self.metadata.get(THE_KEY); return value is True`. `THE_KEY` never appears
       in the return's own expression, so closure growth cannot see it. An RHS that IS a bare
       tracked reference is skipped: that is the followable alias-hop feature, and counting it
       here would double-count one event.

    2. A `return`/`yield`/`yield from` value expression referencing a tracked symbol in a
       function that did NOT itself end up tracked -- hop limit, locally-bound-name shadowing,
       or any rule this function does not know about. A safety net, so an accessor-shaped
       function closure growth could not promote is surfaced somewhere. Skipped when
       *scope_is_tracked*, since that function's own name is already a tracked occurrence and
       flagging its return would call one location both tracked and opaque.

    Both are measured, never classified: nothing here says what the value is used for past
    this point."""
    hops: list[tuple[ast.stmt, str, tuple[str, ...]]] = []
    for stmt in flat_stmts:
        target: ast.Name | None = None
        value: ast.expr | None = None
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            target, value = stmt.targets[0], stmt.value
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            target, value = stmt.target, stmt.value
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            target, value = stmt.target, stmt.value

        if target is not None and value is not None:
            if isinstance(value, ast.Name) and value.id in tracked_names:
                continue  # bare copy: the existing alias-hop feature follows this
            involved = _tracked_refs_in_expr(value, tracked_names)
            if not involved:
                continue
            used_again = any(
                isinstance(n, ast.Name)
                and n.id == target.id
                and isinstance(n.ctx, ast.Load)
                for other_stmt in flat_stmts
                for n in ast.walk(other_stmt)
            )
            if used_again:
                hops.append((stmt, target.id, involved))
            continue

        if scope_is_tracked:
            continue  # this scope's own name is already a tracked occurrence; don't double-flag
        value_exprs: list[ast.expr] = []
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            value_exprs.append(stmt.value)
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.Yield, ast.YieldFrom)) and sub.value is not None:
                value_exprs.append(sub.value)
        for return_value in value_exprs:
            involved = _tracked_refs_in_expr(return_value, tracked_names)
            if involved:
                hops.append((stmt, "<return>", involved))

    return hops


# --------------------------------------------------------------------------
# Symbol closure (definition-site alias tracking across the whole tree)
# --------------------------------------------------------------------------

CLOSURE_RULE_SEED = "seed"
CLOSURE_RULE_STRING_LITERAL = "string-literal-binding"
CLOSURE_RULE_NAME_ALIAS = "name-alias"
CLOSURE_RULE_OWN_NAME = "own-name"
#: A function joins the closure when a tracked symbol is referenced anywhere within a
#: return/yield VALUE EXPRESSION -- data flowing out of the function, scoped to what is
#: returned rather than to the function's body in general.
#:
#: Intentionally hard to move in either direction, because both edges have been over-run:
#: widen it to any reference in the BODY and a function that merely consults a tracked symbol
#: while computing something else joins as though it carried the value, so closure size scales
#: with how finely a tree is factored (subject `command` grew to a 19-name closure including
#: `main`, 58% false-positive occurrences). Narrow it to "the return value must BE a bare
#: Name/Attribute" and it tests the author's punctuation instead: `return A and B and
#: entry.subject and C` is rejected where an equivalent `if not A: return False` /
#: `return entry.subject` is accepted, so a stylistic three-line rewrite of one predicate body
#: moved a real tree's reported occurrences from 5 to 11 with no architectural change.
CLOSURE_RULE_RETURNS_TRACKED = "returns-tracked"


@dataclasses.dataclass(frozen=True)
class _WholeTreeAssignment:
    """A module-level or class-level `NAME = <expr>` / `NAME: T = <expr>` statement, found
    anywhere in the tree. Function-local assignments are deliberately out of scope here; the
    per-occurrence alias-hop feature covers those for a single occurrence's own
    classification."""

    file: str
    line: int
    target_name: str
    source_kind: str  # "string_literal" | "name"
    source_value: str  # the literal string text, or the referenced name


@dataclasses.dataclass(frozen=True)
class _WholeTreeDef:
    """A function/method/class definition found anywhere in the tree, with the names it
    references anywhere within a `return`/`yield`/`yield from` VALUE EXPRESSION. A class is
    recorded with an empty *returned_names*; only its name is collected.

    *returned_names* is collected by walking each such expression, so `return bool(NAME)`,
    `return NAME or default` and `return f(NAME)` all count, not only a bare `return NAME`;
    from every such statement in the def's OWN scope (via :func:`_flatten_scope_statements`,
    so if/for/while/with/try/match bodies are included but nested function/class/lambda bodies
    are not); minus every name locally bound anywhere within it, so a same-spelled parameter
    is not mistaken for a return of an outer tracked symbol. The scoping to what is RETURNED
    is the rule's whole point -- see :data:`CLOSURE_RULE_RETURNS_TRACKED`."""

    file: str
    line: int
    name: str
    returned_names: frozenset[str]


def _locally_bound_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names plus every name a Store/Del-context Name binds anywhere inside
    *func_node*, nested scopes included -- a deliberately conservative over-approximation.
    Stops a same-spelled local shadow being credited as "this function returns the tracked
    symbol"."""
    names: set[str] = set()
    args = func_node.args
    for arg_list in (args.posonlyargs, args.args, args.kwonlyargs):
        names.update(a.arg for a in arg_list)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    for node in ast.walk(func_node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
    return names


def _collect_whole_tree_facts(
    trees: dict[str, ast.Module],
) -> tuple[list[_WholeTreeAssignment], list[_WholeTreeDef]]:
    """One pass over every successfully-parsed file in the tree, building the two fact tables
    :func:`compute_symbol_closure` grows from. Whole-tree (cross-file) by design -- a constant
    and the function that reads it are routinely in different files."""
    assignments: list[_WholeTreeAssignment] = []
    defs: list[_WholeTreeDef] = []

    def scan_simple_assignments(body: list[ast.stmt], file_label: str) -> None:
        for stmt in body:
            target: ast.Name | None = None
            value: ast.expr | None = None
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                target, value = stmt.targets[0], stmt.value
            elif (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.value is not None
            ):
                target, value = stmt.target, stmt.value
            if target is None or value is None:
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                assignments.append(
                    _WholeTreeAssignment(
                        file_label,
                        stmt.lineno,
                        target.id,
                        "string_literal",
                        value.value,
                    )
                )
            elif isinstance(value, ast.Name):
                assignments.append(
                    _WholeTreeAssignment(
                        file_label, stmt.lineno, target.id, "name", value.id
                    )
                )

    for file_label, tree in trees.items():
        scan_simple_assignments(tree.body, file_label)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                scan_simple_assignments(node.body, file_label)
                defs.append(
                    _WholeTreeDef(file_label, node.lineno, node.name, frozenset())
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                locally_bound = _locally_bound_names(node)
                # Collected unfiltered -- the match against whatever is tracked at a given
                # hop happens later, per hop, in _closure_growth_candidates.
                referenced: set[str] = set()
                for stmt in _flatten_scope_statements(node.body):
                    value_exprs: list[ast.expr] = []
                    if isinstance(stmt, ast.Return) and stmt.value is not None:
                        value_exprs.append(stmt.value)
                    for sub in ast.walk(stmt):
                        if (
                            isinstance(sub, (ast.Yield, ast.YieldFrom))
                            and sub.value is not None
                        ):
                            value_exprs.append(sub.value)
                    for value in value_exprs:
                        for n in ast.walk(value):
                            if isinstance(n, ast.Name):
                                referenced.add(n.id)
                            elif isinstance(n, ast.Attribute):
                                referenced.add(n.attr)
                referenced -= locally_bound
                defs.append(
                    _WholeTreeDef(
                        file_label, node.lineno, node.name, frozenset(referenced)
                    )
                )

    return assignments, defs


@dataclasses.dataclass(frozen=True)
class ClosureMember:
    """One symbol in the tracked closure, with a fully auditable reason: which rule admitted
    it, from which already-tracked symbol, at which hop, and where its own definition is."""

    name: str
    hop: int
    rule: str
    reason: str
    location: str | None  # "file:line", or None for a seed subject


@dataclasses.dataclass(frozen=True)
class ClosureCandidate:
    """A symbol that would join the closure exactly one hop past the limit -- reported so a
    truncated chain is visible, never merged into the tracked set. Only one hop beyond the
    limit is probed, so a chain needing hop_limit + 2 does not appear here either."""

    name: str
    would_be_hop: int
    rule: str
    reason: str
    location: str | None


@dataclasses.dataclass(frozen=True)
class ClosureResult:
    hop_limit: int
    members: dict[str, ClosureMember]  # includes the seed subject(s) at hop 0
    excluded: list[ClosureCandidate]

    @property
    def tracked_names(self) -> list[str]:
        return sorted(self.members)


def _closure_growth_candidates(
    assignments: list[_WholeTreeAssignment],
    defs: list[_WholeTreeDef],
    subject_set: set[str],
    tracked: dict[str, ClosureMember],
    hop: int,
) -> dict[str, ClosureMember]:
    """Symbols that would join the closure at exactly *hop*, given the symbols already in
    *tracked* (covering hops 0..hop-1). A pure function with no awareness of any hop limit --
    the caller decides whether to merge the result (real growth) or only report it (the
    excluded-by-hop-limit probe)."""
    newly: dict[str, ClosureMember] = {}

    def consider(name: str, rule: str, reason: str, location: str | None) -> None:
        if name in tracked or name in newly or name in subject_set:
            return
        newly[name] = ClosureMember(
            name=name, hop=hop, rule=rule, reason=reason, location=location
        )

    for a in assignments:
        if (
            hop == 1
            and a.source_kind == "string_literal"
            and a.source_value in subject_set
        ):
            consider(
                a.target_name,
                CLOSURE_RULE_STRING_LITERAL,
                f"assigned the subject string literal {a.source_value!r} at {a.file}:{a.line}",
                f"{a.file}:{a.line}",
            )
        elif (
            a.source_kind == "name"
            and a.source_value in tracked
            and tracked[a.source_value].hop == hop - 1
        ):
            consider(
                a.target_name,
                CLOSURE_RULE_NAME_ALIAS,
                f"assigned from tracked symbol '{a.source_value}' (hop {hop - 1}) at "
                f"{a.file}:{a.line}",
                f"{a.file}:{a.line}",
            )

    if hop == 1:
        for d in defs:
            if d.name in subject_set:
                consider(
                    d.name,
                    CLOSURE_RULE_OWN_NAME,
                    f"definition name equals the subject at {d.file}:{d.line}",
                    f"{d.file}:{d.line}",
                )

    for d in defs:
        returns_at_prev_hop = sorted(
            n for n in d.returned_names if n in tracked and tracked[n].hop == hop - 1
        )
        if returns_at_prev_hop:
            origin_name = returns_at_prev_hop[0]
            consider(
                d.name,
                CLOSURE_RULE_RETURNS_TRACKED,
                f"directly returns tracked symbol '{origin_name}' (hop {hop - 1}) at "
                f"{d.file}:{d.line}",
                f"{d.file}:{d.line}",
            )

    return newly


def compute_symbol_closure(
    trees: dict[str, ast.Module], subjects: Sequence[str], hop_limit: int
) -> ClosureResult:
    """Grows the tracked symbol set from *subjects* by definition-site analysis only, never
    name similarity (:func:`_closure_growth_candidates` holds the rules). Runs at most
    *hop_limit* growth rounds, stopping early once a round adds nothing, then one extra
    unmerged probe round purely to populate :attr:`ClosureResult.excluded`, so a chain cut off
    by the limit is reported rather than dropped."""
    subject_set = set(subjects)
    assignments, defs = _collect_whole_tree_facts(trees)

    members: dict[str, ClosureMember] = {
        s: ClosureMember(
            name=s,
            hop=0,
            rule=CLOSURE_RULE_SEED,
            reason="original subject",
            location=None,
        )
        for s in subject_set
    }

    hop = 0
    while hop < hop_limit:
        hop += 1
        newly = _closure_growth_candidates(assignments, defs, subject_set, members, hop)
        if not newly:
            break  # nothing grew; further rounds up to hop_limit would find nothing either
        members.update(newly)

    probe_hop = hop_limit + 1
    excluded_raw = _closure_growth_candidates(
        assignments, defs, subject_set, members, probe_hop
    )
    excluded = [
        ClosureCandidate(
            name=m.name,
            would_be_hop=m.hop,
            rule=m.rule,
            reason=m.reason,
            location=m.location,
        )
        for m in sorted(excluded_raw.values(), key=lambda m: m.name)
    ]

    return ClosureResult(hop_limit=hop_limit, members=members, excluded=excluded)


# --------------------------------------------------------------------------
# Per-file analysis
# --------------------------------------------------------------------------


def _enclosing_statement_span(node: ast.AST, idx: _TreeIndex) -> tuple[int, int]:
    """The smallest enclosing ``ast.stmt``'s full ``(lineno, end_lineno)`` span, found by
    walking up *node*'s parents. This, not the occurrence's own line, is what a
    changed-line-restricted analysis must test: a multi-line statement can change meaning
    entirely -- a subject moved from a call argument into a branch test, a DECISION's comparand
    edited -- while difflib marks only ANOTHER line of that same statement as changed. Falls
    back to the node's own line as a single-line span if no enclosing statement is found."""
    current = node
    for _ in range(MAX_WALK_DEPTH):
        if isinstance(current, ast.stmt):
            end = getattr(current, "end_lineno", None) or current.lineno
            return current.lineno, end
        info = idx.parent_map.get(id(current))
        if info is None:
            break
        current = info[0]
    start = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", None) or start
    return start, end


def analyze_source(
    source: str,
    file_label: str,
    subjects: Sequence[str],
    allowed_lines: set[int] | None,
    is_test: bool,
) -> FileAnalysis:
    """Parses *source* and returns every subject occurrence (restricted to *allowed_lines* if
    given, else every line) with its role(s). The public single-file entry point: it does the
    parsing and delegates to :func:`_analyze_tree`. Never raises on a syntax error -- reports
    it in ``FileAnalysis.parse_error`` instead, so the caller can name the excluded file."""
    try:
        tree = ast.parse(source, filename=file_label)
    except SyntaxError as exc:
        return FileAnalysis(
            file=file_label,
            parse_error=str(exc),
            occurrences=[],
            string_mentions=[],
            is_test=is_test,
        )
    return _analyze_tree(tree, file_label, subjects, allowed_lines, is_test)


def _analyze_tree(
    tree: ast.Module,
    file_label: str,
    subjects: Sequence[str],
    allowed_lines: set[int] | None,
    is_test: bool,
) -> FileAnalysis:
    """Core role-classification logic, operating on an already-parsed tree. *subjects* here is
    whatever the caller wants matched by exact AST identity -- either the bare original
    subject(s), or (from the orchestration functions) a closure-expanded set of tracked symbol
    names."""
    subject_set = set(subjects)
    idx = _build_index(tree)
    occurrences: list[Occurrence] = []
    string_mentions: list[StringMention] = []
    alias_cache: dict[int, dict[str, str]] = {}

    def aliases_for_scope(scope_node: ast.AST) -> dict[str, str]:
        key = id(scope_node)
        if key not in alias_cache:
            flat = _flatten_scope_statements(_scope_body_statements(scope_node))
            alias_cache[key] = _compute_aliases(flat, subject_set)
        return alias_cache[key]

    def line_ok(node: ast.AST) -> bool:
        """Whether *node*'s ENCLOSING STATEMENT -- not the node's own line -- overlaps
        *allowed_lines*. See :func:`_enclosing_statement_span` for why the distinction
        matters."""
        if allowed_lines is None:
            return True
        start, end = _enclosing_statement_span(node, idx)
        return any(line in allowed_lines for line in range(start, end + 1))

    def record(
        node: ast.AST,
        subject: str,
        kind: str,
        roles: frozenset[str],
        notes: tuple[str, ...],
        via_alias: bool,
        alias_chain: tuple[str, ...],
    ) -> None:
        occurrences.append(
            Occurrence(
                file=file_label,
                line=node.lineno,
                col=node.col_offset,
                subject=subject,
                kind=kind,
                roles=tuple(sorted(roles, key=_role_sort_key)),
                via_alias=via_alias,
                alias_chain=alias_chain,
                notes=notes,
                is_test=is_test,
            )
        )

    for node in idx.name_nodes:
        if not line_ok(node):
            continue
        if node.id in subject_set:
            roles, notes = _classify_ctx_node(node, idx)
            record(node, node.id, "name", roles, notes, via_alias=False, alias_chain=())
        elif isinstance(node.ctx, ast.Load):
            scope = idx.scope_of.get(id(node))
            if scope is None:
                continue
            origin = aliases_for_scope(scope).get(node.id)
            if origin is not None:
                roles, notes = _classify_ctx_node(node, idx)
                record(
                    node,
                    origin,
                    "name",
                    roles,
                    notes,
                    via_alias=True,
                    alias_chain=(node.id,),
                )

    for node in idx.attribute_nodes:
        if node.attr in subject_set and line_ok(node):
            roles, notes = _classify_ctx_node(node, idx)
            record(
                node,
                node.attr,
                "attribute",
                roles,
                notes,
                via_alias=False,
                alias_chain=(),
            )

    for arg_node in idx.arg_nodes:
        if arg_node.arg in subject_set and line_ok(arg_node):
            record(
                arg_node,
                arg_node.arg,
                "arg",
                frozenset({ROLE_CEREMONY}),
                ("function/method signature parameter declaration",),
                via_alias=False,
                alias_chain=(),
            )

    for def_node in idx.def_nodes:
        if def_node.name in subject_set and line_ok(def_node):
            record(
                def_node,
                def_node.name,
                "def-name",
                frozenset({ROLE_WRITE}),
                (
                    "`def`/`class` statement -- binds this name in its enclosing scope, the "
                    "same as an assignment target (e.g. a `@property` computing the subject's "
                    "value under its own name); NOTE: this only catches the definition site "
                    "itself -- if the function body reads the real value through a "
                    "differently-named constant or parameter (as `rule_entry.py`'s "
                    "`allow_in_auto_mode` property does via `ALLOW_IN_AUTO_MODE_KEY`), the "
                    "body's own decision logic is a separate, invisible blind spot -- see "
                    "KNOWN LIMITATIONS.",
                ),
                via_alias=False,
                alias_chain=(),
            )

    for alias_node in idx.alias_nodes:
        matched = None
        if alias_node.name in subject_set:
            matched = alias_node.name
        elif alias_node.asname and alias_node.asname in subject_set:
            matched = alias_node.asname
        if matched and line_ok(alias_node):
            record(
                alias_node,
                matched,
                "import-alias",
                frozenset({ROLE_CEREMONY}),
                ("import statement",),
                via_alias=False,
                alias_chain=(),
            )

    for kw_node in idx.keyword_nodes:
        if kw_node.arg is not None and kw_node.arg in subject_set and line_ok(kw_node):
            record(
                kw_node,
                kw_node.arg,
                "keyword-name",
                frozenset({ROLE_CONDUIT}),
                ("call-site keyword-argument name",),
                via_alias=False,
                alias_chain=(),
            )

    for handler in idx.except_handlers:
        if handler.name and handler.name in subject_set and line_ok(handler):
            record(
                handler,
                handler.name,
                "except-name",
                frozenset({ROLE_WRITE}),
                ("`except ... as name` binding",),
                via_alias=False,
                alias_chain=(),
            )

    for match_as in idx.match_as_nodes:
        if match_as.name and match_as.name in subject_set and line_ok(match_as):
            record(
                match_as,
                match_as.name,
                "match-as",
                frozenset({ROLE_WRITE}),
                ("match-case capture pattern binding",),
                via_alias=False,
                alias_chain=(),
            )

    for match_star in idx.match_star_nodes:
        if match_star.name and match_star.name in subject_set and line_ok(match_star):
            record(
                match_star,
                match_star.name,
                "match-star",
                frozenset({ROLE_WRITE}),
                ("match-case `*name` capture binding",),
                via_alias=False,
                alias_chain=(),
            )

    for match_mapping in idx.match_mapping_nodes:
        if (
            match_mapping.rest
            and match_mapping.rest in subject_set
            and line_ok(match_mapping)
        ):
            record(
                match_mapping,
                match_mapping.rest,
                "match-mapping-rest",
                frozenset({ROLE_WRITE}),
                ("match-case `**rest` capture binding",),
                via_alias=False,
                alias_chain=(),
            )

    for global_node in idx.global_nodes:
        for name in global_node.names:
            if name in subject_set and line_ok(global_node):
                record(
                    global_node,
                    name,
                    "global",
                    frozenset({ROLE_CEREMONY}),
                    ("`global` scope declaration",),
                    via_alias=False,
                    alias_chain=(),
                )

    for nonlocal_node in idx.nonlocal_nodes:
        for name in nonlocal_node.names:
            if name in subject_set and line_ok(nonlocal_node):
                record(
                    nonlocal_node,
                    name,
                    "nonlocal",
                    frozenset({ROLE_CEREMONY}),
                    ("`nonlocal` scope declaration",),
                    via_alias=False,
                    alias_chain=(),
                )

    for const_node in idx.string_constants:
        if const_node.value in subject_set and line_ok(const_node):
            string_mentions.append(
                StringMention(
                    file=file_label,
                    line=const_node.lineno,
                    col=const_node.col_offset,
                    subject=const_node.value,
                    is_test=is_test,
                )
            )

    opaque_hops: list[OpaqueHop] = []
    for scope_node in idx.scope_nodes:
        flat = _flatten_scope_statements(_scope_body_statements(scope_node))
        # A function whose own name already joined the closure has its returns visible through
        # its def-name occurrence; flagging them as opaque too would call one location both
        # tracked and opaque. Only unpromoted scopes need the return-based safety net.
        scope_is_tracked = (
            isinstance(scope_node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and scope_node.name in subject_set
        )
        for stmt, local_name, involved in _find_opaque_hops_in_scope(
            flat, subject_set, scope_is_tracked
        ):
            if line_ok(stmt):
                opaque_hops.append(
                    OpaqueHop(
                        file=file_label,
                        line=stmt.lineno,
                        col=stmt.col_offset,
                        local_name=local_name,
                        tracked_symbols_involved=involved,
                        is_test=is_test,
                    )
                )

    return FileAnalysis(
        file=file_label,
        parse_error=None,
        occurrences=occurrences,
        string_mentions=string_mentions,
        opaque_hops=opaque_hops,
        is_test=is_test,
    )


# --------------------------------------------------------------------------
# Changed-line computation (two-tree / git-diff modes)
# --------------------------------------------------------------------------


def compute_changed_lines(old_text: str, new_text: str) -> set[int]:
    """New-side 1-based line numbers touched by an 'insert' or 'replace' opcode between
    *old_text* and *new_text*. A line only removed (present in old, absent in new) has no
    new-side location and is intentionally not in this set."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            changed.update(range(j1 + 1, j2 + 1))
    return changed


# --------------------------------------------------------------------------
# Analysis orchestration
# --------------------------------------------------------------------------


@dataclasses.dataclass
class AnalysisResult:
    mode: str
    subjects: list[str]
    files_analyzed: list[FileAnalysis]
    parse_failures: list[str]  # human-readable "path: message"
    removed_files: list[str]  # present only in the OLD side (two-tree/git-diff modes)
    closure: ClosureResult
    #: Files gathered ONLY for whole-tree closure discovery, and so never in ``files_analyzed``
    #: or ``parse_failures``, that failed to parse. A file here means closure growth is
    #: incomplete, which has to stay visible even though the file was not part of the diff
    #: being reported.
    closure_parse_failures: list[str] = dataclasses.field(default_factory=list)


def _try_parse(source: str, label: str) -> tuple[ast.Module | None, str | None]:
    try:
        return ast.parse(source, filename=label), None
    except SyntaxError as exc:
        return None, str(exc)


def _read_python_source(path: Path) -> tuple[str | None, str | None]:
    """Reads *path* respecting a PEP 263 encoding cookie or a UTF-8 BOM, via the stdlib
    `tokenize.detect_encoding`. Returns ``(source, None)`` on success or ``(None, message)`` on
    ANY failure -- a broken symlink, a permission-denied file, a directory whose name happens
    to match `*.py`, an undecodable file. Callers report the message like a parse failure, so
    one bad file in a large tree is named and excluded rather than aborting the run."""
    try:
        with path.open("rb") as fh:
            encoding, _ = tokenize.detect_encoding(fh.readline)
        with path.open(
            "r", encoding=encoding, errors="surrogateescape", newline=""
        ) as fh:
            return fh.read(), None
    except (OSError, SyntaxError, UnicodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


@dataclasses.dataclass
class _ParsedFile:
    label: str
    is_test: bool
    tree: ast.Module | None
    parse_error: str | None
    allowed_lines: set[int] | None


def _run_pipeline(
    mode: str,
    subjects: Sequence[str],
    closure_trees: dict[str, ast.Module],
    analyzed_files: list[_ParsedFile],
    closure_hop_limit: int,
    removed_files: list[str],
    closure_parse_failures: list[str] | None = None,
) -> AnalysisResult:
    """Shared second half of every input mode.

    *closure_trees* is the WHOLE tree being examined and is used only to grow the tracked
    symbol set, because a constant and the function that reads it are routinely in a file that
    never itself changed. *analyzed_files* is the subset the caller wants reported -- every
    file for ``--tree``, only the changed and added ones for the diff modes -- and is
    classified against the closure-expanded tracked names, never against the bare subjects
    alone. *closure_parse_failures* names files fetched only for closure discovery that failed
    to parse; see :attr:`AnalysisResult.closure_parse_failures`."""
    closure = compute_symbol_closure(closure_trees, subjects, closure_hop_limit)
    tracked_names = closure.tracked_names

    parse_failures = [
        f"{pf.label}: {pf.parse_error}"
        for pf in analyzed_files
        if pf.parse_error is not None
    ]
    files_analyzed: list[FileAnalysis] = []
    for pf in analyzed_files:
        if pf.tree is None:
            files_analyzed.append(
                FileAnalysis(
                    file=pf.label,
                    parse_error=pf.parse_error,
                    occurrences=[],
                    string_mentions=[],
                    is_test=pf.is_test,
                )
            )
            continue
        files_analyzed.append(
            _analyze_tree(
                pf.tree, pf.label, tracked_names, pf.allowed_lines, pf.is_test
            )
        )

    return AnalysisResult(
        mode=mode,
        subjects=list(subjects),
        files_analyzed=files_analyzed,
        parse_failures=parse_failures,
        removed_files=removed_files,
        closure=closure,
        closure_parse_failures=list(closure_parse_failures or []),
    )


def run_single_tree(
    tree_root: Path,
    subjects: Sequence[str],
    closure_hop_limit: int = DEFAULT_CLOSURE_HOP_LIMIT,
) -> AnalysisResult:
    force_test = _root_forces_test_context(tree_root)
    parsed_files: list[_ParsedFile] = []
    for relpath in discover_python_files(tree_root):
        label = str(relpath)
        is_test = force_test or is_test_path(relpath)
        source, read_error = _read_python_source(tree_root / relpath)
        if source is None:
            parsed_files.append(_ParsedFile(label, is_test, None, read_error, None))
            continue
        tree, error = _try_parse(source, label)
        parsed_files.append(_ParsedFile(label, is_test, tree, error, None))

    closure_trees = {pf.label: pf.tree for pf in parsed_files if pf.tree is not None}
    return _run_pipeline(
        f"single-tree ({tree_root})",
        subjects,
        closure_trees,
        parsed_files,
        closure_hop_limit,
        [],
    )


def run_two_tree_diff(
    old_root: Path,
    new_root: Path,
    subjects: Sequence[str],
    closure_hop_limit: int = DEFAULT_CLOSURE_HOP_LIMIT,
) -> AnalysisResult:
    force_test = _root_forces_test_context(new_root)
    old_relpaths = discover_python_files(old_root)
    new_relpaths = discover_python_files(new_root)
    old_relpath_set = set(old_relpaths)
    new_relpath_set = set(new_relpaths)

    # Read every OLD-side file up front (each is read at most once) so a file that MOVED --
    # identical content, different relative path -- can be matched by content instead of
    # falling through to "brand new". Without it, a byte-identical `pkg/a.py` -> `pkg2/a.py`
    # move reports the WHOLE file as changed, with phantom DECISION/WRITE occurrences. That
    # inflates whichever tree did the moving by exactly the amount of code that moved, and in
    # an architecture-overhaul comparison moving files IS the change.
    old_contents: dict[Path, str | None] = {}
    for relpath in old_relpaths:
        content, _read_error = _read_python_source(old_root / relpath)
        old_contents[relpath] = content

    # Only old paths with NO same-relative-path match in the new tree are eligible move
    # sources -- a same-path file is handled by the ordinary diff branch below.
    move_candidates: dict[str, list[Path]] = {}
    for relpath in old_relpaths:
        if relpath in new_relpath_set:
            continue
        content = old_contents.get(relpath)
        if content is not None:
            move_candidates.setdefault(content, []).append(relpath)

    claimed_move_sources: set[Path] = set()
    parsed_files: list[_ParsedFile] = []
    for relpath in new_relpaths:
        label = str(relpath)
        is_test = force_test or is_test_path(relpath)
        new_source, read_error = _read_python_source(new_root / relpath)
        if new_source is None:
            parsed_files.append(_ParsedFile(label, is_test, None, read_error, None))
            continue
        if relpath in old_relpath_set:
            # A read failure on the OLD side falls back to "no usable pre-image", the same as
            # a genuinely new file, so every line counts as changed.
            old_source = old_contents.get(relpath)
            allowed_lines: set[int] | None = (
                None
                if old_source is None
                else compute_changed_lines(old_source, new_source)
            )
        else:
            candidates = move_candidates.get(new_source, [])
            move_source = next(
                (p for p in candidates if p not in claimed_move_sources), None
            )
            if move_source is not None:
                claimed_move_sources.add(move_source)
                allowed_lines = compute_changed_lines(
                    old_contents[move_source] or "", new_source
                )
            else:
                allowed_lines = (
                    None  # genuinely new content: every line counts as changed
                )
        tree, error = _try_parse(new_source, label)
        parsed_files.append(_ParsedFile(label, is_test, tree, error, allowed_lines))

    removed = sorted(
        str(p) for p in (old_relpath_set - new_relpath_set - claimed_move_sources)
    )
    # The whole NEW tree is already parsed above, changed files or not, so it doubles as the
    # closure-discovery input with no extra work.
    closure_trees = {pf.label: pf.tree for pf in parsed_files if pf.tree is not None}
    return _run_pipeline(
        f"two-tree diff (old={old_root}, new={new_root})",
        subjects,
        closure_trees,
        parsed_files,
        closure_hop_limit,
        removed,
    )


def _git_show(repo: Path, rev: str, path: str) -> str | None:
    """File content at *rev*, or None if the file does not exist there. Fetches raw bytes and
    decodes via :func:`_decode_python_bytes` rather than letting `subprocess.run(text=True)`
    decode strictly, so a PEP 263 cookie or a UTF-8 BOM is honoured. An undecodable blob also
    returns None, which callers cannot tell apart from "not found"."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"],
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        return None
    return _decode_python_bytes(result.stdout)


def _decode_python_bytes(data: bytes) -> str | None:
    """Decodes *data* respecting a PEP 263 encoding cookie or a UTF-8 BOM, the same way
    :func:`_read_python_source` reads from disk. Returns None, never raises, if the bytes
    cannot be decoded at all."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding, errors="surrogateescape")
    except (
        SyntaxError,
        UnicodeError,
        LookupError,
    ):
        return None


def _git_ls_tree_python_files(repo: Path, rev: str) -> list[str]:
    """Every ``*.py`` path tracked at *rev* (not just changed ones) -- used to give closure
    discovery the WHOLE tree, since a constant or reader function relevant to the diff is
    routinely defined in a file the diff never touches."""
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", rev],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".py")]


@dataclasses.dataclass(frozen=True)
class _GitDiffEntry:
    """One line of `git diff --name-status -M` output. *old_path* equals *new_path* unless
    *status* is ``"R"`` (renamed, possibly with content changes too)."""

    #: "A" | "M" | "D" | "R". Any other single-path status is treated like "M";
    #: :func:`_git_diff_entries` drops a two-path status that is not "R".
    status: str
    old_path: str
    new_path: str


def _git_diff_entries(repo: Path, base: str, head: str) -> list[_GitDiffEntry]:
    """Parses `git diff --name-status -M` so a renamed file's PRE-IMAGE is fetched from its
    OLD path, never its new one. Without `-M`, a pure `git mv` with byte-identical content has
    no pre-image AT THE NEW PATH, `allowed_lines` becomes None and the ENTIRE file counts as
    changed -- phantom counts for every moved-but-unchanged file, on exactly the rename-heavy
    diffs an architecture-overhaul comparison produces."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--name-status",
            "-M",
            f"{base}..{head}",
            "--",
            "*.py",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    entries: list[_GitDiffEntry] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0][0]  # "R100" -> "R"; "M"/"A"/"D" already single-character
        if status == "R" and len(fields) == 3:
            entries.append(
                _GitDiffEntry(status="R", old_path=fields[1], new_path=fields[2])
            )
        elif len(fields) == 2:
            entries.append(
                _GitDiffEntry(status=status, old_path=fields[1], new_path=fields[1])
            )
    return entries


def run_git_diff(
    repo: Path,
    base: str,
    head: str,
    subjects: Sequence[str],
    closure_hop_limit: int = DEFAULT_CLOSURE_HOP_LIMIT,
) -> AnalysisResult:
    analyzed_files: list[_ParsedFile] = []
    removed_files: list[str] = []
    for entry in _git_diff_entries(repo, base, head):
        if entry.status == "D":
            removed_files.append(entry.new_path)
            continue
        new_source = _git_show(repo, head, entry.new_path)
        if new_source is None:
            removed_files.append(entry.new_path)  # deleted in head after all
            continue
        if entry.status == "A":
            allowed_lines = None  # newly added path: every line counts as changed
        else:
            # "M", "R" (rename: the pre-image comes from the OLD path), or any rarer status
            # git-diff emits -- fetch the pre-image and diff normally.
            old_source = _git_show(repo, base, entry.old_path)
            allowed_lines = (
                None
                if old_source is None
                else compute_changed_lines(old_source, new_source)
            )
        tree, error = _try_parse(new_source, entry.new_path)
        analyzed_files.append(
            _ParsedFile(
                entry.new_path,
                is_test_path(Path(entry.new_path)),
                tree,
                error,
                allowed_lines,
            )
        )

    # files_analyzed stays scoped to the diff; closure_trees is built separately from the WHOLE
    # tree at *head*, so closure discovery is not blind to a constant or reader function
    # living in a file the diff never touched. Files already attempted above, successfully or
    # not, are never re-fetched.
    closure_trees: dict[str, ast.Module] = {
        pf.label: pf.tree for pf in analyzed_files if pf.tree is not None
    }
    already_attempted = {pf.label for pf in analyzed_files}
    closure_parse_failures: list[str] = []
    for path in _git_ls_tree_python_files(repo, head):
        if path in already_attempted:
            continue
        source = _git_show(repo, head, path)
        if source is None:
            # Undecodable at *head*: the closure shrinks and no bucket names the file.
            # Measured -- a tracked-at-head `*.py` blob with an unusable PEP 263 cookie
            # appears in none of parse_failures, closure_parse_failures, removed_files or
            # the TEST/PRODUCTION lists.
            continue
        tree, error = _try_parse(source, path)
        if tree is not None:
            closure_trees[path] = tree
        else:
            # Outside the diff, so this never reaches `parse_failures`; recorded here instead
            # because a parse error out here shrinks the closure just as silently.
            closure_parse_failures.append(f"{path}: {error}")

    return _run_pipeline(
        f"git diff ({repo}, {base}..{head})",
        subjects,
        closure_trees,
        analyzed_files,
        closure_hop_limit,
        removed_files,
        closure_parse_failures,
    )


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _all_occurrences(result: AnalysisResult) -> list[Occurrence]:
    return [occ for fa in result.files_analyzed for occ in fa.occurrences]


def _all_string_mentions(result: AnalysisResult) -> list[StringMention]:
    return [sm for fa in result.files_analyzed for sm in fa.string_mentions]


def _all_opaque_hops(result: AnalysisResult) -> list[OpaqueHop]:
    return [hop for fa in result.files_analyzed for hop in fa.opaque_hops]


def build_report(result: AnalysisResult) -> dict:
    """The full structured report, feeding both the text and the ``--json`` output so the two
    presentations cannot drift apart. `primary_role_counts` and `all_roles_counts` are
    per-location annotation and are deliberately not combined into a comparative number -- see
    the module docstring."""
    occurrences = _all_occurrences(result)
    string_mentions = _all_string_mentions(result)

    def bucket(occs: list[Occurrence]) -> dict:
        all_roles_counter: Counter[str] = Counter()
        primary_counter: Counter[str] = Counter()
        for occ in occs:
            for role in occ.roles:
                all_roles_counter[role] += 1
            primary_counter[occ.primary_role] += 1
        return {
            "all_roles_counts": dict(all_roles_counter),
            "primary_role_counts": dict(primary_counter),
            "total_occurrences": len(occs),
        }

    prod_occurrences = [o for o in occurrences if not o.is_test]
    test_occurrences = [o for o in occurrences if o.is_test]

    per_file: dict[str, dict] = {}
    for fa in result.files_analyzed:
        if fa.occurrences or fa.string_mentions:
            per_file[fa.file] = bucket(fa.occurrences) | {
                "string_mentions": len(fa.string_mentions)
            }

    # Full file lists behind the test/production split: a path heuristic can misfile a whole
    # tree -- a `spec/` convention, or `--tree` pointed at a subdirectory already inside a
    # test directory -- with nothing wrong showing in the counts.
    test_files = sorted(fa.file for fa in result.files_analyzed if fa.is_test)
    production_files = sorted(fa.file for fa in result.files_analyzed if not fa.is_test)

    closure = result.closure
    closure_members = [
        {
            "name": m.name,
            "hop": m.hop,
            "rule": m.rule,
            "reason": m.reason,
            "location": m.location,
        }
        for m in sorted(closure.members.values(), key=lambda m: (m.hop, m.name))
    ]
    closure_excluded = [
        {
            "name": c.name,
            "would_be_hop": c.would_be_hop,
            "rule": c.rule,
            "reason": c.reason,
            "location": c.location,
        }
        for c in closure.excluded
    ]

    opaque_hops = _all_opaque_hops(result)
    opaque_hops_production = [h for h in opaque_hops if not h.is_test]
    opaque_hops_test = [h for h in opaque_hops if h.is_test]

    def opaque_hop_locations(hops: list[OpaqueHop]) -> list[str]:
        return [
            f"{h.file}:{h.line}:{h.col} -- local '{h.local_name}' from "
            f"{', '.join(h.tracked_symbols_involved)}"
            for h in hops
        ]

    return {
        "mode": result.mode,
        "subjects": result.subjects,
        "test_vs_production_rule": TEST_VS_PRODUCTION_RULE,
        "test_files": test_files,
        "production_files": production_files,
        "files_analyzed": len(result.files_analyzed),
        "parse_failures": result.parse_failures,
        "removed_files": result.removed_files,
        "closure": {
            "hop_limit": closure.hop_limit,
            "tracked_names": closure.tracked_names,
            "members": closure_members,
            "excluded_by_hop_limit": closure_excluded,
            "parse_failures": result.closure_parse_failures,
        },
        "opaque_hops": {
            "explanation": (
                "A tracked symbol's value crosses into a fresh, untracked LOCAL name that is "
                "then used further (e.g. `value = self.metadata.get(THE_KEY); return value is "
                "True`) -- this tool cannot see what happens past that point, so every one of "
                "these is a place a DECISION could be hiding, uncounted. A large difference "
                "between two trees' opaque-hop counts means their DECISION counts are NOT a "
                "fair comparison."
            ),
            "production": len(opaque_hops_production),
            "test": len(opaque_hops_test),
            "total": len(opaque_hops),
            "production_locations": opaque_hop_locations(opaque_hops_production),
            "test_locations": opaque_hop_locations(opaque_hops_test),
        },
        "production": bucket(prod_occurrences),
        "test": bucket(test_occurrences),
        "combined": bucket(occurrences),
        "per_file": per_file,
        "string_literal_mentions": {
            "total": len(string_mentions),
            "production": sum(1 for m in string_mentions if not m.is_test),
            "test": sum(1 for m in string_mentions if m.is_test),
            "locations": [
                f"{m.file}:{m.line}:{m.col} ({'test' if m.is_test else 'production'})"
                for m in string_mentions
            ],
        },
        "unclassified_occurrences": [
            {
                "file": o.file,
                "line": o.line,
                "col": o.col,
                "subject": o.subject,
                "kind": o.kind,
                "notes": list(o.notes),
            }
            for o in occurrences
            if ROLE_UNCLASSIFIED in o.roles
        ],
        # Occurrences carrying a note but NOT already UNCLASSIFIED -- an accumulated CONDUIT
        # under an unhandled parent, or the walrus dual-role note. This is the "a rule is
        # missing here, but a role was still recorded" signal, and it has its own printed
        # section because the UNCLASSIFIED list does not cover it.
        "occurrences_with_notes": [
            {
                "file": o.file,
                "line": o.line,
                "col": o.col,
                "subject": o.subject,
                "kind": o.kind,
                "roles": list(o.roles),
                "notes": list(o.notes),
            }
            for o in occurrences
            if o.notes and ROLE_UNCLASSIFIED not in o.roles
        ],
        "occurrences": [
            {
                "file": o.file,
                "line": o.line,
                "col": o.col,
                "subject": o.subject,
                "kind": o.kind,
                "roles": list(o.roles),
                "primary_role": o.primary_role,
                "via_alias": o.via_alias,
                "alias_chain": list(o.alias_chain),
                "notes": list(o.notes),
                "is_test": o.is_test,
            }
            for o in occurrences
        ],
        "known_limitations": KNOWN_LIMITATIONS,
    }


def print_text_report(report: dict) -> None:
    print(f"change-role classifier -- mode: {report['mode']}")
    print(f"subjects: {', '.join(report['subjects'])}")
    print(f"test-vs-production rule: {report['test_vs_production_rule']}")
    print(f"files analyzed: {report['files_analyzed']}")
    print()
    print(
        "NOTE: this tool no longer publishes a CONDUIT-to-DECISION ratio. An independent "
        "adversarial review showed it is the wrong measure for the question, not merely "
        "buggy -- see KNOWN LIMITATIONS below for why. Its trustworthy outputs are OCCURRENCE "
        "FINDING (verified exact against an independent AST oracle) and the SYMBOL CLOSURE "
        "listing; role labels below are descriptive per-location annotation only."
    )
    print()

    if report["parse_failures"]:
        print(
            f"PARSE FAILURES ({len(report['parse_failures'])}) -- EXCLUDED from all counts below:"
        )
        for failure in report["parse_failures"]:
            print(f"  - {failure}")
        print()
    else:
        print("Parse failures: none.")
        print()

    if report["removed_files"]:
        print(
            f"REMOVED / undiffable files ({len(report['removed_files'])}) -- present on the OLD "
            "side only, not classified against the NEW tree:"
        )
        for path in report["removed_files"]:
            print(f"  - {path}")
        print()

    print(f"TEST files ({len(report['test_files'])}):")
    for path in report["test_files"]:
        print(f"  [test] {path}")
    print(f"PRODUCTION files ({len(report['production_files'])}):")
    for path in report["production_files"]:
        print(f"  [production] {path}")
    print()

    closure = report["closure"]
    print("=" * 70)
    print(f"SYMBOL CLOSURE (hop limit: {closure['hop_limit']})")
    print("=" * 70)
    print(
        "The subject is a NAME, not a value -- this closure is every additional symbol "
        "tracked as an occurrence of it, found by DEFINITION-SITE analysis only (never name "
        "similarity), plus WHY each one joined. Audit this before trusting the counts above:"
    )
    for m in closure["members"]:
        if m["hop"] == 0:
            print(f"  [seed]  {m['name']}")
        else:
            loc = f" ({m['location']})" if m["location"] else ""
            print(f"  [hop {m['hop']}] {m['name']} -- {m['reason']}{loc}")
    print()
    if closure["excluded_by_hop_limit"]:
        print(
            f"CLOSURE: excluded by hop limit ({len(closure['excluded_by_hop_limit'])}) -- would "
            "have joined one hop further than the limit allows; NEVER silently dropped:"
        )
        for c in closure["excluded_by_hop_limit"]:
            loc = f" ({c['location']})" if c["location"] else ""
            print(
                f"  [would be hop {c['would_be_hop']}] {c['name']} -- {c['reason']}{loc}"
            )
    else:
        print("CLOSURE: nothing excluded by the hop limit.")
    if closure["parse_failures"]:
        print(
            f"CLOSURE: {len(closure['parse_failures'])} file(s) OUTSIDE the reported set "
            "failed to parse while being fetched only for closure discovery -- closure growth "
            "is incomplete for a reason this tool cannot see past, and is NOT reflected in "
            "the PARSE FAILURES list above (that list is scoped to files_analyzed only):"
        )
        for failure in closure["parse_failures"]:
            print(f"  - {failure}")
    print()

    def print_bucket(label: str, bucket: dict) -> None:
        print(f"-- {label} --")
        print(f"  total occurrences: {bucket['total_occurrences']}")
        print(
            f"  primary-role counts (precedence DECISION>WRITE>CONDUIT>CEREMONY): {bucket['primary_role_counts']}"
        )
        print(
            f"  all-roles counts (an occurrence may count in more than one): {bucket['all_roles_counts']}"
        )
        print()

    print("=" * 70)
    print(
        "ROLE BREAKDOWN (descriptive per-location annotation -- NOT a comparative score; "
        "no ratio is published, see the NOTE at the top of this report)"
    )
    print("=" * 70)
    print(
        "CAVEAT on DECISION counts below: `X or Y` (BoolOp) is scored DECISION "
        "unconditionally, without confirming the result is actually branch-tested -- a value "
        "used purely for defaulting (`flag or default`) still labels DECISION. This is not "
        "hypothetical on the real trees this tool was built to examine: one of the two "
        "production DECISIONs on the unrefactored validation tree is produced by this rule "
        "(a BoolOp being assigned, tested one line later, but the tool does not check that). "
        "See KNOWN LIMITATIONS for the full account and why this was not fixed."
    )
    print()
    print_bucket("PRODUCTION", report["production"])
    print_bucket("TEST", report["test"])
    print_bucket("COMBINED (production + test)", report["combined"])

    oh = report["opaque_hops"]
    print(
        "-- OPAQUE HOPS (not classified, MEASURED so the DECISION counts can be trusted) --"
    )
    print(f"  {oh['explanation']}")
    print(f"  production: {oh['production']}, test: {oh['test']}, total: {oh['total']}")
    for loc in oh["production_locations"]:
        print(f"  [production] {loc}")
    for loc in oh["test_locations"]:
        print(f"  [test] {loc}")
    print()

    sm = report["string_literal_mentions"]
    print(
        f"String-literal exact-match mentions of the subject (NOT role-classified -- "
        f"see KNOWN LIMITATIONS): {sm['total']} total "
        f"({sm['production']} production, {sm['test']} test)"
    )
    print()

    unclassified = report["unclassified_occurrences"]
    print(
        f"UNCLASSIFIED occurrences (explicit -- never folded into a zero): {len(unclassified)}"
    )
    for item in unclassified:
        print(
            f"  - {item['file']}:{item['line']}:{item['col']} ({item['kind']}) -- {item['notes']}"
        )
    print()

    with_notes = report["occurrences_with_notes"]
    print(
        f"OCCURRENCES WITH NOTES (a role WAS assigned, but the walk hit something worth "
        f"flagging along the way -- e.g. an unhandled construct beyond an accumulated hop "
        f'role; this is the "a rule is missing here" signal, not hidden in --json only): '
        f"{len(with_notes)}"
    )
    for item in with_notes:
        print(
            f"  - {item['file']}:{item['line']}:{item['col']} ({item['kind']}, "
            f"roles={item['roles']}) -- {item['notes']}"
        )
    print()

    print("KNOWN LIMITATIONS (what this tool structurally cannot see):")
    for i, limitation in enumerate(report["known_limitations"], start=1):
        print(f"  {i}. {limitation}")
    print()

    print("Per-file breakdown (files with at least one occurrence or string mention):")
    for file, bucket_data in sorted(report["per_file"].items()):
        print(
            f"  {file}: {bucket_data['primary_role_counts']} "
            f"(string mentions: {bucket_data['string_mentions']})"
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify every occurrence of one or more subject identifiers by the role it "
            "plays (DECISION/WRITE/CONDUIT/CEREMONY) at each changed code location."
        )
    )
    parser.add_argument(
        "--subject",
        action="append",
        required=True,
        dest="subjects",
        help="Identifier introduced/changed by the requirement. Repeatable.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--tree", type=Path, help="Single-tree mode: analyze every occurrence."
    )
    mode_group.add_argument(
        "--old", type=Path, help="Two-tree diff mode: OLD tree (use with --new)."
    )
    mode_group.add_argument(
        "--repo", type=Path, help="Git-diff mode: repo path (use with --base/--head)."
    )
    parser.add_argument(
        "--new", type=Path, help="Two-tree diff mode: NEW tree (use with --old)."
    )
    parser.add_argument(
        "--base", help="Git-diff mode: base revision (use with --repo/--head)."
    )
    parser.add_argument(
        "--head", help="Git-diff mode: head revision (use with --repo/--base)."
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the machine-readable report as JSON."
    )
    parser.add_argument(
        "--closure-hops",
        type=int,
        default=DEFAULT_CLOSURE_HOP_LIMIT,
        help=(
            "How many definition-site hops (constant bindings, reader functions) the symbol "
            "closure is allowed to grow beyond the bare subject(s) before stopping. "
            f"Default: {DEFAULT_CLOSURE_HOP_LIMIT}. Printed in every report, and every symbol "
            "that joined -- and why -- is listed in the SYMBOL CLOSURE section."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.tree is not None:
        if not args.tree.is_dir():
            print(f"{args.tree} is not a directory", file=sys.stderr)
            return 2
        result = run_single_tree(args.tree, args.subjects, args.closure_hops)
    elif args.old is not None:
        if args.new is None:
            print("--old requires --new", file=sys.stderr)
            return 2
        result = run_two_tree_diff(args.old, args.new, args.subjects, args.closure_hops)
    else:
        if not (args.base and args.head):
            print("--repo requires --base and --head", file=sys.stderr)
            return 2
        result = run_git_diff(
            args.repo, args.base, args.head, args.subjects, args.closure_hops
        )

    report = build_report(result)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
