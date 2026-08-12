"""
Deterministic helpers behind the toolguard skills and config tooling.

Deliberately off the runtime permission-evaluation path: ``.pyscn.toml`` puts
this package in the ``tooling`` layer, which every layer below it is denied
from importing.
"""
