#!/usr/bin/env python3
"""Validate protocol structure, behavior, runtime references, and profile safety."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


DEFAULT_SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "delegated-execution-protocol"
EXPECTED_PROFILES = {
    "delegated_batch_explorer": ("gpt-5.6-luna", "low", "read-only"),
    "delegated_explorer": ("gpt-5.6-terra", "low", "read-only"),
    "delegated_researcher": ("gpt-5.6-terra", "medium", "read-only"),
    "delegated_deep_researcher": ("gpt-5.6-terra", "high", "read-only"),
    "delegated_batch_worker": ("gpt-5.6-luna", "medium", "workspace-write"),
    "delegated_worker": ("gpt-5.6-terra", "medium", "workspace-write"),
    "delegated_complex_worker": ("gpt-5.6-terra", "high", "workspace-write"),
    "delegated_senior_worker": ("gpt-5.6-sol", "high", "workspace-write"),
    "delegated_reviewer": ("gpt-5.6-sol", "high", "read-only"),
    "delegated_planning_auditor": ("gpt-5.6-sol", "xhigh", "read-only"),
}
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "evals/evals.json",
    "references/reporting.md",
    "references/runtime-transports.md",
    "scripts/select_agent_profile.py",
    "scripts/test_select_agent_profile.py",
    "scripts/validate_protocol.py",
}
ROUTING_FIELDS = {
    "Task",
    "Kind",
    "Writes",
    "Scope",
    "Task size",
    "Risk",
    "Ambiguity",
    "Independent evidence",
    "Parallel value",
    "Priority",
    "Workload",
    "Batch size",
    "Verification",
    "Coordination",
    "Steering trigger",
    "Requested workers",
    "Sharding evidence",
    "Transport preference",
    "Selected profile / transport",
    "Assignment evidence",
}
SELECTOR_OPTIONS = {
    "--kind",
    "--writes",
    "--scope",
    "--task-size",
    "--risk",
    "--ambiguity",
    "--independent-evidence",
    "--parallel-value",
    "--priority",
    "--workload",
    "--batch-size",
    "--verification",
    "--coordination",
    "--steering-trigger",
    "--requested-workers",
    "--sharding-evidence",
    "--transport-preference",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"validation failed: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument(
        "--check-local-profiles",
        action="store_true",
        help="also verify a local Codex profile installation under --codex-home",
    )
    return parser.parse_args()


def parse_frontmatter(content: str) -> dict[str, str]:
    match = re.match(r"\A---\n(?P<body>.*?)\n---\n", content, re.DOTALL)
    require(match is not None, "SKILL.md frontmatter is malformed")
    result: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        require(bool(separator and key.strip() and value.strip()), "frontmatter must use key: value lines")
        result[key.strip()] = value.strip()
    return result


def markdown_links(content: str) -> set[str]:
    return set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", content))


def cache_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            continue
        stat = path.stat()
        snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def validate_skill_structure(skill_root: Path) -> None:
    present = {
        str(path.relative_to(skill_root))
        for path in skill_root.rglob("*")
        if path.is_file()
    }
    require(REQUIRED_FILES <= present, f"missing required files: {sorted(REQUIRED_FILES - present)}")

    skill_path = skill_root / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(skill)
    require(frontmatter.get("name") == SKILL_NAME, "skill name changed")
    require(set(frontmatter) == {"name", "description"}, "frontmatter fields drifted")
    require(bool(frontmatter["description"]), "skill description is empty")

    headings = re.findall(r"^##\s+(.+)$", skill, re.MULTILINE)
    require(len(headings) >= 10, "SKILL.md lacks the expected workflow structure")
    require(len(headings) == len(set(headings)), "SKILL.md contains duplicate sections")

    route_fields = {
        match.group(1).strip()
        for match in re.finditer(r"^(.*?):(?:\s|$)", skill, re.MULTILINE)
        if match.group(1).strip() in ROUTING_FIELDS
    }
    require(route_fields == ROUTING_FIELDS, f"routing record fields drifted: {sorted(ROUTING_FIELDS - route_fields)}")
    for profile in EXPECTED_PROFILES:
        require(f"`{profile}`" in skill, f"missing profile {profile}")
    for model in {profile[0] for profile in EXPECTED_PROFILES.values()}:
        require(model in skill, f"missing model tier {model}")
    require("gpt-5.5" not in skill, "stale gpt-5.5 policy remains")

    links = markdown_links(skill)
    expected_links = {"references/runtime-transports.md", "references/reporting.md"}
    require(expected_links <= links, "SKILL.md does not link both runtime references")
    for link in links:
        if "://" in link or link.startswith("#"):
            continue
        require((skill_root / link).is_file(), f"broken local reference: {link}")

    require("PYTHONDONTWRITEBYTECODE=1" in skill, "main validation command can generate cache")
    require("python3 scripts/validate_protocol.py" in skill, "main validation command is not self-contained")


def validate_openai_metadata(skill_root: Path) -> None:
    content = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    require(re.search(r"^interface:\s*$", content, re.MULTILINE) is not None, "openai.yaml lacks interface")
    values = dict(re.findall(r'^\s{2}(display_name|short_description|default_prompt):\s+"(.+)"$', content, re.MULTILINE))
    require(set(values) == {"display_name", "short_description", "default_prompt"}, "openai.yaml interface fields drifted")
    require(f"${SKILL_NAME}" in values["default_prompt"], "default_prompt does not invoke this skill")
    require(25 <= len(values["short_description"]) <= 64, "short_description length is outside 25-64 chars")
    require(any("\u4e00" <= char <= "\u9fff" for char in "".join(values.values())), "UI metadata is not localized")


def validate_runtime_references(skill_root: Path) -> None:
    runtime = (skill_root / "references" / "runtime-transports.md").read_text(encoding="utf-8")
    reporting = (skill_root / "references" / "reporting.md").read_text(encoding="utf-8")
    for token in ("fork_turns", "turn_context", "explicit-codex-cli", "verified-inherited-collaboration", "探测"):
        require(token in runtime or token in (skill_root / "SKILL.md").read_text(encoding="utf-8"), f"runtime contract lacks {token}")
    require(reporting.count("```text") >= 3, "reporting reference lacks route examples")
    for token in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        require(token in reporting, f"reporting reference lacks {token} example")


def validate_selector_behavior(skill_root: Path, cache_before: dict[str, tuple[int, int]]) -> None:
    selector = skill_root / "scripts" / "select_agent_profile.py"
    tests = skill_root / "scripts" / "test_select_agent_profile.py"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    help_result = subprocess.run(
        [sys.executable, str(selector), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    require(help_result.returncode == 0, f"selector --help failed:\n{help_result.stderr}")
    missing_options = {option for option in SELECTOR_OPTIONS if option not in help_result.stdout}
    require(not missing_options, f"selector CLI options are missing: {sorted(missing_options)}")

    test_result = subprocess.run(
        [sys.executable, str(tests)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    require(test_result.returncode == 0, f"profile selector tests failed:\n{test_result.stderr}")
    require(cache_snapshot(skill_root) == cache_before, "validation generated or modified Python cache")


def validate_profile_safety(codex_home: Path) -> None:
    config_path = codex_home / "config.toml"
    catalog_path = codex_home / "models_cache.json"
    require(config_path.is_file(), f"missing Codex config {config_path}")
    require(catalog_path.is_file(), f"missing model catalog {catalog_path}")

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    registered_agents = config.get("agents", {})
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    supported = {
        item["slug"]: {
            level["effort"]
            for level in item.get("supported_reasoning_levels", [])
            if isinstance(level, dict) and isinstance(level.get("effort"), str)
        }
        for item in catalog.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    }

    for name, (model, effort, sandbox) in EXPECTED_PROFILES.items():
        profile_path = codex_home / "agents" / f"{name}.toml"
        require(profile_path.is_file(), f"missing custom agent {profile_path}")
        registration = registered_agents.get(name, {})
        require(registration.get("config_file") == f"agents/{name}.toml", f"{name} registration drifted")
        require(bool(registration.get("description")), f"{name} registration has no description")
        profile = tomllib.loads(profile_path.read_text(encoding="utf-8"))
        required_fields = {"name", "description", "developer_instructions", "model", "model_reasoning_effort"}
        require(all(profile.get(field) for field in required_fields), f"{profile_path} lacks required fields")
        require(profile["name"] == name, f"{profile_path} name mismatch")
        require(profile["model"] == model, f"{profile_path} model drift")
        require(profile["model_reasoning_effort"] == effort, f"{profile_path} effort drift")
        require(profile.get("sandbox_mode") == sandbox, f"{profile_path} sandbox drift")
        require(effort in supported.get(model, set()), f"catalog does not support {model}/{effort}")


def validate_evals(skill_root: Path) -> int:
    evals = json.loads((skill_root / "evals" / "evals.json").read_text(encoding="utf-8"))
    require(evals.get("skill_name") == SKILL_NAME, "eval skill_name mismatch")
    cases = evals.get("evals")
    require(isinstance(cases, list) and len(cases) >= 20, "at least twenty eval cases are required")
    ids = [case.get("id") for case in cases]
    require(len(ids) == len(set(ids)), "eval ids must be unique")
    for case in cases:
        require(isinstance(case.get("id"), int), "eval id must be an integer")
        require(bool(case.get("prompt")), f"eval {case.get('id')} has no prompt")
        require(bool(case.get("expected_output")), f"eval {case.get('id')} has no expected output")
        require(isinstance(case.get("files"), list), f"eval {case.get('id')} files must be a list")
        expectations = case.get("expectations")
        require(isinstance(expectations, list) and len(expectations) >= 3, f"eval {case.get('id')} needs at least three expectations")
    return len(cases)


def main() -> None:
    args = parse_args()
    skill_root = args.skill_root.resolve()
    codex_home = args.codex_home.resolve()
    cache_before = cache_snapshot(skill_root)
    require(
        not cache_before,
        f"skill source contains Python cache artifacts: {sorted(cache_before)}",
    )
    sys.dont_write_bytecode = True

    validate_skill_structure(skill_root)
    validate_openai_metadata(skill_root)
    validate_runtime_references(skill_root)
    validate_selector_behavior(skill_root, cache_before)
    if args.check_local_profiles:
        validate_profile_safety(codex_home)
    eval_count = validate_evals(skill_root)
    require(not cache_snapshot(skill_root), "protocol validation generated Python cache")
    print(f"protocol validation passed: {eval_count} eval cases; cache absent")


if __name__ == "__main__":
    main()
