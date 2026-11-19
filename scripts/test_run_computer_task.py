#!/usr/bin/env python3
"""Run the local computer-task regression tests."""
from computer_runtime import load_runtime_code

# Keep this module's filename so the runtime can import sibling protocol modules.
exec(load_runtime_code(__file__))
