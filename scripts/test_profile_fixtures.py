"""Synthetic model bindings for tests only; runtime bindings live in Codex agent TOMLs."""
from pathlib import Path
from agent_profiles import ROLE_SANDBOX

TEST_BINDINGS = {
    "delegated_batch_explorer": ("gpt-6-luna", "high"),
    "delegated_batch_worker": ("gpt-6-luna", "high"),
    "delegated_explorer": ("gpt-6-luna", "high"),
    "delegated_researcher": ("gpt-6.1-sol", "medium"),
    "delegated_deep_researcher": ("gpt-6.1-sol", "high"),
    "delegated_standard_reviewer": ("gpt-6.1-sol", "high"),
    "delegated_worker": ("gpt-6.1-sol", "medium"),
    "delegated_computer_worker": ("gpt-6.1-terra", "medium"),
    "delegated_complex_worker": ("gpt-6.1-sol", "high"),
    "delegated_senior_worker": ("gpt-6-astra", "high"),
    "delegated_reviewer": ("gpt-6-astra", "high"),
    "delegated_planning_auditor": ("gpt-6-astra", "xhigh"),
}

def binding(home: Path, role: str) -> dict[str, str]:
    model, effort = TEST_BINDINGS[role]
    return {"agent_name": role, "model": model, "model_reasoning_effort": effort,
            "sandbox_mode": ROLE_SANDBOX[role], "config_file": str(home / "agents" / f"{role}.toml")}

def write_profiles(home: Path) -> None:
    (home / "agents").mkdir(parents=True, exist_ok=True)
    for role in TEST_BINDINGS:
        b = binding(home, role)
        (home / "agents" / f"{role}.toml").write_text(
            f'name = "{role}"\ndescription = "Test role"\ndeveloper_instructions = "Use assigned ownership"\n'
            f'model = "{b["model"]}"\nmodel_reasoning_effort = "{b["model_reasoning_effort"]}"\n'
            f'sandbox_mode = "{b["sandbox_mode"]}"\n', encoding="utf-8")
