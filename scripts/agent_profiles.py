"""Load protocol role bindings from Codex config; no production model defaults here."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

ROLE_SANDBOX = {
    "delegated_batch_explorer": "read-only",
    "delegated_explorer": "read-only",
    "delegated_researcher": "read-only",
    "delegated_deep_researcher": "read-only",
    "delegated_standard_reviewer": "read-only",
    "delegated_batch_worker": "workspace-write",
    "delegated_worker": "workspace-write",
    "delegated_computer_worker": "workspace-write",
    "delegated_complex_worker": "workspace-write",
    "delegated_senior_worker": "workspace-write",
    "delegated_reviewer": "read-only",
    "delegated_planning_auditor": "read-only",
}


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"cannot read configuration {path}: {exc}") from exc


def home_config(home: Path) -> dict[str, Any]:
    path = home / "config.toml"
    return read_toml(path) if path.exists() else {}


def catalog_path(home: Path, explicit: Path | None = None) -> Path:
    home = home.expanduser().resolve()
    if explicit is not None:
        return explicit
    value = home_config(home).get("model_catalog_json")
    path = Path(value).expanduser() if value else home / "models_cache.json"
    return path if path.is_absolute() else home / path


def load_binding(home: Path, role: str) -> dict[str, str]:
    home = home.expanduser().resolve()
    if role not in ROLE_SANDBOX:
        raise SystemExit(f"unknown protocol role: {role}")
    registration = home_config(home).get("agents", {}).get(role, {})
    value = registration.get("config_file", f"agents/{role}.toml")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = home / path
    profile = read_toml(path)
    for key in ("name", "description", "developer_instructions", "model", "model_reasoning_effort"):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise SystemExit(f"profile {role} requires explicit {key}: {path}")
    if profile["name"] != role:
        raise SystemExit(f"profile name mismatch: {role}: {path}")
    if profile.get("sandbox_mode") != ROLE_SANDBOX[role]:
        raise SystemExit(f"unsafe sandbox for {role}: expected {ROLE_SANDBOX[role]}")
    if "permissions" in profile or "default_permissions" in profile:
        raise SystemExit(f"conflicting permission override in {role}; use its explicit sandbox contract")
    return {
        "agent_name": role,
        "model": profile["model"],
        "model_reasoning_effort": profile["model_reasoning_effort"],
        "sandbox_mode": profile["sandbox_mode"],
        "config_file": str(path.resolve()),
    }


def resolve_catalog(path: Path, model: str, effort: str) -> tuple[str, str, None]:
    if not path.is_file():
        raise SystemExit(f"model catalog unavailable: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        models = data["models"]
        if not isinstance(models, list):
            raise ValueError("models must be an array")
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"invalid model catalog {path}: {exc}") from exc
    for item in models:
        if not isinstance(item, dict) or item.get("slug") != model:
            continue
        levels = item.get("supported_reasoning_levels", [])
        if isinstance(levels, list) and any(isinstance(x, dict) and x.get("effort") == effort for x in levels):
            return model, effort, None
    raise SystemExit(f"required profile unavailable: {model}/{effort}")
