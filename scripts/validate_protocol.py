#!/usr/bin/env python3
"""Validate protocol structure, behavior, runtime references, and profile safety."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_profiles import ROLE_SANDBOX, catalog_path, default_codex_home, load_binding, resolve_catalog


DEFAULT_SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "delegated-execution-protocol"

REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "evals/evals.json",
    "references/reporting.md",
    "references/routing-policy.md",
    "references/runtime-transports.md",
    "scripts/select_agent_profile.py",
    "scripts/agent_profiles.py",
    "scripts/test_profile_fixtures.py",
    "scripts/test_select_agent_profile.py",
    "scripts/test_validate_protocol.py",
    "scripts/validate_protocol.py",
    "scripts/preflight_dispatch.py",
    "scripts/test_preflight_dispatch.py",
    "scripts/run_computer_task.py",
    "scripts/test_run_computer_task.py",
    "references/computer-tasks.md",
}
ROUTING_FIELDS = {"Task", "Ownership", "Delegation value", "Acceptance", "Assignment", "Outcome"}

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
    "--sensitivity",
    "--coordination",
    "--steering-trigger",
    "--requested-workers",
    "--sharding-evidence",
    "--transport-preference",
    "--codex-home",
    "--native-binding",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"validation failed: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
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
    require(len(headings) == len(set(headings)), "SKILL.md contains duplicate sections")

    routing = (skill_root / "references/routing-policy.md").read_text(encoding="utf-8")
    route_fields = {
        match.group(1).strip()
        for match in re.finditer(r"^(.*?):(?:\s|$)", routing, re.MULTILINE)
        if match.group(1).strip() in ROUTING_FIELDS
    }
    require(route_fields == ROUTING_FIELDS, f"routing record fields drifted: {sorted(ROUTING_FIELDS - route_fields)}")
    for profile in ROLE_SANDBOX:
        require(f"`{profile}`" in routing, f"missing profile {profile}")

    links = markdown_links(skill)
    expected_links = {"references/runtime-transports.md", "references/reporting.md", "references/routing-policy.md"}
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
    routing = (skill_root / "references" / "routing-policy.md").read_text(encoding="utf-8")
    verified_at_match = re.search(r"^verified_at:\s*(\d{4}-\d{2}-\d{2})\s*$", runtime, re.MULTILINE)
    require(verified_at_match is not None, "runtime verified_at is missing or malformed")
    verified_at = date.fromisoformat(verified_at_match.group(1))
    verification_age = (date.today() - verified_at).days
    require(verification_age >= 0, "runtime verification is future-dated")
    require(re.search(r"^verification_surface:\s*.+$", runtime, re.MULTILINE) is not None, "runtime verification surface is missing")
    for token in (
        "preflight_dispatch.py",
        "dispatchable",
        "model_unavailable",
        "turn_context",
        "agent_type",
        "reasoning_effort",
        "explicit-codex-cli",
        "native-named-agent",
    ):
        require(token in runtime or token in routing or token in (skill_root / "SKILL.md").read_text(encoding="utf-8"), f"runtime contract lacks {token}")


def validate_selector_behavior(skill_root: Path, cache_before: dict[str, tuple[int, int]]) -> None:
    selector = skill_root / "scripts" / "select_agent_profile.py"
    tests = skill_root / "scripts" / "test_select_agent_profile.py"
    validator_tests = skill_root / "scripts" / "test_validate_protocol.py"
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

    validator_test_result = subprocess.run(
        [sys.executable, str(validator_tests)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    require(
        validator_test_result.returncode == 0,
        f"static/manual contract validator tests failed:\n{validator_test_result.stderr}",
    )
    preflight_tests = subprocess.run(
        [sys.executable, str(skill_root / "scripts" / "test_preflight_dispatch.py")],
        capture_output=True, text=True, check=False, env=env,
    )
    require(preflight_tests.returncode == 0, f"dispatch preflight tests failed:\n{preflight_tests.stderr}")
    sync_tests = subprocess.run(
        [sys.executable, str(skill_root / "scripts" / "test_sync_skills_manager.py")],
        capture_output=True, text=True, check=False, env=env,
    )
    require(sync_tests.returncode == 0, f"Skills Manager sync gate tests failed:\n{sync_tests.stderr}")
    computer_tests = subprocess.run(
        [sys.executable, str(skill_root / "scripts" / "test_run_computer_task.py")],
        capture_output=True, text=True, check=False, env=env,
    )
    require(computer_tests.returncode == 0, f"computer approval client tests failed:\n{computer_tests.stderr}")
    require(cache_snapshot(skill_root) == cache_before, "validation generated or modified Python cache")


def validate_profile_safety(codex_home: Path) -> None:
    path = catalog_path(codex_home)
    for role in ROLE_SANDBOX:
        profile = load_binding(codex_home, role)
        resolve_catalog(path, profile["model"], profile["model_reasoning_effort"])


def fixture_catalog(path: Path) -> None:
    supported: dict[str, set[str]] = {}
    from test_profile_fixtures import TEST_BINDINGS
    for model, effort in TEST_BINDINGS.values():
        supported.setdefault(model, set()).add(effort)
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": model,
                        "supported_reasoning_levels": [
                            {"effort": effort} for effort in sorted(efforts)
                        ],
                    }
                    for model, efforts in sorted(supported.items())
                ]
            }
        ),
        encoding="utf-8",
    )


def validate_static_contract_checks(skill_root: Path, case: dict[str, object]) -> int:
    case_id = case.get("id")
    checks = case.get("contract_checks")
    require(
        isinstance(checks, list) and bool(checks),
        f"eval {case_id} manual contract needs non-empty contract_checks",
    )
    root = skill_root.resolve()
    for index, check in enumerate(checks, start=1):
        require(
            isinstance(check, dict)
            and set(check) == {"path", "required_tokens"},
            f"eval {case_id} contract check {index} must contain only path and required_tokens",
        )
        target = check.get("path")
        require(
            isinstance(target, str) and bool(target.strip()),
            f"eval {case_id} contract check {index} has an invalid path",
        )
        relative_path = Path(target)
        require(
            not relative_path.is_absolute() and ".." not in relative_path.parts,
            f"eval {case_id} contract check {index} has an unsafe target path: {target}",
        )
        resolved = (root / relative_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            require(
                False,
                f"eval {case_id} contract check {index} escapes the skill root: {target}",
            )
        require(
            resolved.is_file(),
            f"eval {case_id} contract check {index} target does not exist: {target}",
        )
        required_tokens = check.get("required_tokens")
        require(
            isinstance(required_tokens, list)
            and bool(required_tokens)
            and all(isinstance(token, str) and bool(token.strip()) for token in required_tokens),
            f"eval {case_id} contract check {index} needs non-empty required_tokens",
        )
        content = resolved.read_text(encoding="utf-8")
        for token in required_tokens:
            require(
                token in content,
                f"eval {case_id} contract check {index} missing required token {token!r} in {target}",
            )
    return len(checks)


def validate_evals(skill_root: Path) -> tuple[int, int, int, int]:
    evals = json.loads((skill_root / "evals" / "evals.json").read_text(encoding="utf-8"))
    require(evals.get("skill_name") == SKILL_NAME, "eval skill_name mismatch")
    cases = evals.get("evals")
    require(isinstance(cases, list) and len(cases) >= 20, "at least twenty eval cases are required")
    ids = [case.get("id") for case in cases]
    require(len(ids) == len(set(ids)), "eval ids must be unique")
    executable_count = 0
    manual_count = 0
    static_contract_check_count = 0
    selector = skill_root / "scripts" / "select_agent_profile.py"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory() as temp_dir:
        catalog = Path(temp_dir) / "models_cache.json"
        fixture_catalog(catalog)
        from test_profile_fixtures import binding, write_profiles
        write_profiles(Path(temp_dir))
        for case in cases:
            require(isinstance(case.get("id"), int), "eval id must be an integer")
            require(bool(case.get("prompt")), f"eval {case.get('id')} has no prompt")
            require(bool(case.get("expected_output")), f"eval {case.get('id')} has no expected output")
            require(isinstance(case.get("files"), list), f"eval {case.get('id')} files must be a list")
            expectations = case.get("expectations")
            require(isinstance(expectations, list) and len(expectations) >= 3, f"eval {case.get('id')} needs at least three expectations")
            route_args = case.get("route_args")
            expected_route = case.get("expected_route")
            expected_route_contains = case.get("expected_route_contains")
            manual_contract = case.get("manual_contract")
            contract_checks = case.get("contract_checks")
            require(
                (route_args is not None and manual_contract is None and contract_checks is None)
                or (route_args is None and manual_contract is True),
                f"eval {case.get('id')} must be executable or explicitly manual_contract=true",
            )
            require(
                (route_args is None) == (expected_route is None),
                f"eval {case.get('id')} must provide route_args and expected_route together",
            )
            require(
                expected_route_contains is None or route_args is not None,
                f"eval {case.get('id')} expected_route_contains requires route_args",
            )
            if route_args is None:
                static_contract_check_count += validate_static_contract_checks(
                    skill_root, case
                )
                manual_count += 1
                continue
            require(isinstance(route_args, list) and all(isinstance(item, str) for item in route_args), f"eval {case.get('id')} route_args must be a string list")
            require(isinstance(expected_route, dict) and expected_route, f"eval {case.get('id')} expected_route must be a non-empty object")
            result = subprocess.run(
                [sys.executable, str(selector), *route_args, "--catalog", str(catalog), "--codex-home", temp_dir, *[arg for role in ROLE_SANDBOX for arg in ("--native-binding", json.dumps(binding(Path(temp_dir), role)))]],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            require(result.returncode == 0, f"eval {case.get('id')} selector failed:\n{result.stderr}")
            actual = json.loads(result.stdout)
            for key, expected in expected_route.items():
                require(actual.get(key) == expected, f"eval {case.get('id')} expected {key}={expected!r}, got {actual.get(key)!r}")
            if expected_route_contains is not None:
                require(isinstance(expected_route_contains, dict), f"eval {case.get('id')} expected_route_contains must be an object")
                for key, expected_items in expected_route_contains.items():
                    actual_items = actual.get(key)
                    require(isinstance(actual_items, list) and isinstance(expected_items, list), f"eval {case.get('id')} expected list containment for {key}")
                    require(all(item in actual_items for item in expected_items), f"eval {case.get('id')} missing expected {key} entries")
            executable_count += 1
    require(executable_count >= 5, "at least five eval cases must execute the selector")
    require(executable_count + manual_count == len(cases), "eval accounting mismatch")
    require(
        static_contract_check_count >= manual_count,
        "every manual contract needs at least one static contract check",
    )
    return len(cases), executable_count, manual_count, static_contract_check_count


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
    (
        eval_count,
        executable_eval_count,
        manual_eval_count,
        static_contract_check_count,
    ) = validate_evals(skill_root)
    require(not cache_snapshot(skill_root), "protocol validation generated Python cache")
    print(
        f"protocol validation passed: {eval_count} eval definitions validated; "
        f"{executable_eval_count} executable routes passed; "
        f"{manual_eval_count} static/manual contract cases passed via "
        f"{static_contract_check_count} file-token checks (not end-to-end behavior); "
        "selector and contract-validator tests passed; cache absent"
    )


if __name__ == "__main__":
    main()
