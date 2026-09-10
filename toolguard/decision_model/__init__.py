"""Decision model: the permission vocabulary a decision is expressed in.

Rule entries, verdicts, level matches, provenance and the context protocols the
engine resolves against. Sits directly above ``foundation`` and below both
``configuration`` and ``engine``, so the decision machinery can share this
vocabulary with the configuration layer without depending on it (TOO-78).
"""
