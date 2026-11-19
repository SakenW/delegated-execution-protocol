#!/usr/bin/env python3
"""Run the local computer-task client."""
from pathlib import Path

runtime_script = Path("/Volumes/工作盘/_Codex/skills/delegated-execution-protocol-runtime") / Path(__file__).name

# Keep this module's filename so the runtime can import sibling protocol modules.
exec(compile(runtime_script.read_bytes(), str(runtime_script), "exec"))
