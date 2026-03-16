#!/usr/bin/env bash
# Wrapper script to invoke toolguard hook with the correct Python environment.
# This script is referenced from Claude Code hook configurations in settings.local.json.
exec /Users/arnon/projects/toolguard/.venv/bin/python -m toolguard.hook "$@"
