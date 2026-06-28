---
title: TOO-15 P2-A.1 Coder Task Recall
type: note
permalink: toolguard/implementation/too-15-p2-a.1-coder-task-recall
tags:
- TOO-15
- task-memory
- coder-recall
- P2-A1
---

# TOO-15 P2-A.1 Keystone Slice - Coder Task Recall

## Task
Implement `toolguard/tools/consolidate.py` + `test/unit/test_tools_consolidate.py`
- Library-only Python: NO CLI, NO file I/O, NO skill in this slice
- Ticket: TOO-15 / TOO-11

## Critical process constraint
BEFORE writing any code, inventory and reuse:
- `toolguard/tools/replay.py` — `replay(corpus, config_a, config_b) -> ReplayDiff`
- `toolguard/tools/redundancy.py` — study `_config_without_allow` for synthetic config technique
- `toolguard/tools/config_access.py` — `per_layer_rules(config, tool) -> List[LayerRules]`
- `toolguard/tools/decision.py` — `decide(config, tool, command, extended_syntax=True) -> Decision`
- `toolguard/patterns.py` — `parse_pattern(pattern, extended_syntax=True) -> (PatternType, body)`
- `toolguard/config.py` — `Configuration`, `ConfigLayer`, `Provenance`

## Step 0: Generalize synthetic-config primitive
Add `with_layer_allow_replaced(config, tool, provenance, removed: Set[str], added: List[str]) -> Configuration`
- Location: `config_access.py` or new `toolguard/tools/config_mutate.py` (check for circular imports)
- Same MappingProxyType content-rebuild technique as `_config_without_allow`
- NOTE: layer `content["permissions"]["allow"]` stores WRAPPED patterns like `Bash(git diff:*)`, while `LayerRules.allow` is wrapper-free
- Refactor `redundancy._config_without_allow` to delegate to this new primitive
- Confirm existing redundancy tests still pass

## Step 1: Family 1 - Literal-alternation consolidation
- Per layer, per list (allow only)
- Detect groups of >= 2 patterns that are `PatternType.default`
- Token-identical EXCEPT exactly ONE token slot which varies over LITERAL values
- Split body on first `:` into (command, args)
- Real target: `git diff:*`, `git flake8:*`, etc. -> `[regex]^git (diff|flake8|...)\b...`
- STRICT acceptance requires BOTH:
  (a) Self-contained probe equivalence
  (b) Historical replay: `replay(corpus, A, B).broadened_count == 0`
- If either fails, do NOT emit

## Step 2: Family 2 - Static subsumption elimination
- Per layer, per list (allow only)
- Detect rule whose STATIC match-set is a provable SUBSET of another rule
- No corpus needed (corpus-independent)
- Be CONSERVATIVE: only claim subsumption when structurally provable
- Propose DROPPING the subsumed rule
- Use replay as secondary guard when corpus present

## Data model
```python
@dataclass(frozen=True)
class ConsolidationProposal:
    kind: str            # 'literal-alternation' | 'static-subsumption'
    tool: str
    list_type: str       # 'allow'
    layer_provenance: Provenance
    removed_patterns: Tuple[str, ...]
    added_pattern: Optional[str]
    rationale: str
    replay_summary: str  # short evidence string

def propose_consolidations(config, tool, corpus=None) -> List[ConsolidationProposal]:
    ...
```

## Tests (stdlib unittest, BDD docstrings)
- Family-1 git-family happy path (accepted)
- Alembic landmine REJECTED (ask->allow broadening)
- Family-2 mkdir subsumption (accepted drop)
- Family-2 conservative NON-claim
- Step-0 primitive correctness
- `_config_without_allow` still behaves (redundancy tests green)

## Dev gotchas
- Tests: `uv run python -m unittest discover -s test -t .` (NOT pytest)
- Syntax check: `uv run python -m py_compile <files>`
- Lint: `uv run ruff check .` (DO NOT run `ruff format`)
- NO async/await, NO threading, NO local imports
- Every function/class gets a doc comment

## Started: Phase 1 (Planning)
