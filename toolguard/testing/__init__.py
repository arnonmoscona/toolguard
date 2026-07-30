"""
Test and experiment support for toolguard.

This subpackage is NOT imported by any production code path -- the hook, the
resolver, and the tooling commands never depend on it. It exists so that
behavioural questions about toolguard ("what would this config decide for this
command?") can be answered against a fully isolated, throwaway project instead
of by editing live configuration.

See :mod:`toolguard.testing.sandbox`.
"""
