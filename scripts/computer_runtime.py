"""Load the configured computer runtime for the two skill entry scripts."""

from pathlib import Path
from types import CodeType

from agent_profiles import default_codex_home


def load_runtime_code(entry_file: str) -> CodeType:
    config = default_codex_home() / "delegated-execution-protocol-runtime.path"
    try:
        runtime_dir = Path(config.read_text(encoding="utf-8").strip()).expanduser()
    except OSError as exc:
        raise SystemExit(f"Cannot read computer runtime configuration {config}: {exc}") from exc

    if not runtime_dir.is_absolute():
        raise SystemExit(f"Set an absolute runtime directory in {config}")

    script = runtime_dir / Path(entry_file).name
    try:
        source = script.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read computer runtime script {script}: {exc}") from exc

    return compile(source, str(script), "exec")
