import sys
import trace
import unittest

tracer = trace.Trace(
    count=True,
    trace=False,
    ignoredirs=[sys.prefix, sys.exec_prefix],  # skip the stdlib itself
)

def _run():
    suite = unittest.TestLoader().discover('test', top_level_dir='.')
    unittest.TextTestRunner(verbosity=1).run(suite)

tracer.runfunc(_run)
tracer.results().write_results(show_missing=True, summary=True, coverdir='cover')
