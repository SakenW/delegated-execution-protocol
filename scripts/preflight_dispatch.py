#!/usr/bin/env python3
"""Check the exact configured CLI binding; never substitute a model/provider."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from agent_profiles import ROLE_SANDBOX, default_codex_home, home_config, load_binding, read_toml

TOKEN = "DELEGATION_PROBE_OK"
PROFILE_KEYS = {"name", "description", "model", "model_reasoning_effort", "sandbox_mode",
                "developer_instructions", "model_provider"}


def classify_failure(message: str, timed_out: bool = False) -> tuple[str, str]:
    text = message.lower()
    if timed_out:
        return "timeout", "CLI 探针超时；模型可用性未确认。"
    if re.search(r"unexpected argument|unrecognized (?:argument|option)|unknown (?:argument|option)", text):
        return "cli_argument_unsupported", "CLI 拒绝启动参数；检查实际二进制及其 exec --help。"
    if "reasoning" in text and any(x in text for x in ("not supported", "unsupported", "invalid")):
        return "effort_unavailable", "当前模型/provider 不接受配置推理档位；不得自动降低 effort 或换模型。"
    if ("model" in text and any(x in text for x in ("not supported", "not found", "not available", "does not exist"))) or "model_not_found" in text:
        return "model_unavailable", "当前 CLI 账户/provider 不接受配置模型；CLI 已接受参数。不得自动换模型或 provider。"
    if any(x in text for x in ("unauthorized", "authentication", "401", "please log in", "not logged in")):
        return "authentication_failed", "CLI 身份认证失败；尚不能判断模型可用性。"
    if any(x in text for x in ("rate_limit", "rate limit", "429", "quota exceeded")):
        return "rate_limited", "CLI 请求受速率或额度限制；尚不能判断模型可用性。"
    if any(x in text for x in ("connection refused", "connection reset", "dns", "timed out", "failed to connect", "error sending request")):
        return "network_failed", "CLI 网络请求失败；尚不能判断模型可用性。"
    if any(x in text for x in ("error loading config", "invalid config", "toml parse")):
        return "configuration_failed", "CLI 配置加载失败；尚未验证模型。"
    return "execution_failed", "CLI 探针未完成；检查本地证据，不推断为模型或参数不支持。"


def summarize_events(path: Path) -> tuple[bool, str | None, str, str]:
    completed, thread_id, answer = False, None, ""
    errors = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
        elif kind == "turn.completed":
            completed = True
        elif kind in ("error", "turn.failed"):
            errors.append(str(event.get("message") or event.get("error")))
        elif kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            answer = event["item"].get("text", "").strip()
    return completed and not errors, thread_id, answer, "\n".join(errors)


def runtime_binding(home: Path, thread_id: str | None) -> dict | None:
    if not thread_id or not re.fullmatch(r"[0-9a-f-]{36}", thread_id):
        return None
    for path in (home / "sessions").glob(f"*/*/*/rollout-*{thread_id}.jsonl"):
        latest, provider = None, None
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "session_meta":
                    provider = event.get("payload", {}).get("model_provider")
                if event.get("type") == "turn_context":
                    payload = event["payload"]
                    latest = {"model": payload.get("model"),
                              "model_reasoning_effort": payload.get("effort"),
                              "sandbox_mode": payload.get("sandbox_policy", {}).get("type")}
        if latest:
            latest["model_provider"] = provider
            return latest
    return None


def prepare(home: Path, role: str, cli: str) -> tuple[dict, list[str]]:
    binding = load_binding(home, role)
    profile = read_toml(Path(binding["config_file"]))
    extra = set(profile) - PROFILE_KEYS
    if extra:
        raise SystemExit("unsupported role configuration; cannot apply full binding: " + ", ".join(sorted(extra)))
    config = home_config(home)
    provider = profile.get("model_provider", config.get("model_provider"))
    if provider is not None and (not isinstance(provider, str) or not provider.strip()):
        raise SystemExit("model_provider must be a nonempty string")
    executable = shutil.which(cli)
    if not executable:
        raise SystemExit("CLI executable unavailable")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15)
    help_result = subprocess.run([executable, "exec", "--help"], capture_output=True, text=True, timeout=15)
    if version.returncode or help_result.returncode:
        raise SystemExit("CLI capability inspection failed")
    required = ["--model", "--config", "--sandbox", "--json", "--cd", "--skip-git-repo-check"]
    if any(flag not in help_result.stdout for flag in required):
        raise SystemExit("CLI lacks required flags; inspect exec --help")
    digest = hashlib.sha256()
    for path in [home / "config.toml", Path(binding["config_file"]), home / "auth.json"]:
        digest.update(path.read_bytes() if path.exists() else b"<missing>")
    digest.update((executable + version.stdout).encode())
    result = {**binding, "transport": "explicit-codex-cli", "codex_home": str(home),
              "provider": provider or "<CLI default>", "cli": executable,
              "cli_version": version.stdout.strip(), "binding_fingerprint": digest.hexdigest(),
              "dispatchable": False, "status": "probe_required",
              "message": "配置与 CLI 参数可用；尚未验证账户/provider 可调用此模型。"}
    argv = [executable, "exec", "--model", binding["model"], "--sandbox", binding["sandbox_mode"],
            "-c", "model_reasoning_effort=" + json.dumps(binding["model_reasoning_effort"]),
            "-c", "developer_instructions=" + json.dumps(profile["developer_instructions"], ensure_ascii=False)]
    if "model_provider" in profile:
        argv += ["-c", "model_provider=" + json.dumps(provider)]
    return result, argv


def probe(home: Path, result: dict, argv: list[str], output: Path, timeout: int) -> dict:
    output = output.expanduser().resolve()
    # Explicit output ownership: never overwrite an earlier probe or fall back to system tmp.
    output.mkdir(parents=True, exist_ok=False)
    stdout_path, stderr_path = output / "events.jsonl", output / "stderr.log"
    env = os.environ.copy()
    env.update(CODEX_HOME=str(home), TMPDIR=str(output), TMP=str(output), TEMP=str(output), PYTHONDONTWRITEBYTECODE="1")
    argv = argv + ["--cd", str(output), "--skip-git-repo-check", "--json", "-"]
    timed_out = False
    with stdout_path.open("w") as out, stderr_path.open("w") as err:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                   text=True, env=env, start_new_session=True)
        try:
            process.communicate("Availability probe only. Do not call tools or access files/network. Reply exactly " + TOKEN, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    completed, thread_id, answer, error = summarize_events(stdout_path)
    result.update(exit_code=process.returncode, thread_id=thread_id, evidence_dir=str(output),
                  probe_completed=completed and process.returncode == 0 and answer == TOKEN)
    status_match = re.search(r'["\']status["\']\s*:\s*(\d{3})', error)
    if status_match:
        result["http_status"] = int(status_match.group(1))
    if timed_out or not result["probe_completed"]:
        status, message = classify_failure(error or stderr_path.read_text(errors="replace"), timed_out)
        result.update(status=status, message=message)
    else:
        observed = runtime_binding(home, thread_id)
        expected = {key: result[key] for key in ("model", "model_reasoning_effort", "sandbox_mode")}
        result["observed_binding"] = observed
        matched = bool(observed) and all(observed.get(key) == value for key, value in expected.items())
        if result["provider"] != "<CLI default>":
            matched = matched and observed.get("model_provider") == result["provider"]
        result.update(dispatchable=matched, status="verified" if matched else "runtime_binding_unverified",
                      message="配置模型已完成探针，运行 model/effort/权限匹配。" if matched else
                      "模型请求已完成，但运行 model/effort/权限缺失或不匹配；不得派发正式任务。")
        if matched and result["agent_name"] == "delegated_computer_worker":
            result.update(dispatchable=False, status="capability_probe_required",
                          required_capabilities=["computer-use", "target-app-access"],
                          message="模型绑定已验证；仍须在同一 transport 验证电脑工具、目标应用访问和操作后状态，才可派发正式任务。")
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=sorted(ROLE_SANDBOX))
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--cli", default="codex")
    parser.add_argument("--probe", action="store_true", help="Make one minimal model request; may consume quota")
    parser.add_argument("--output-dir", type=Path, help="New evidence directory on the approved work volume")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.timeout < 1 or args.timeout > 300:
        parser.error("timeout must be between 1 and 300 seconds")
    if args.probe and args.output_dir is None:
        parser.error("--probe requires --output-dir")
    try:
        result, argv = prepare(args.codex_home.expanduser().resolve(), args.role, args.cli)
        if args.probe:
            result = probe(args.codex_home.expanduser().resolve(), result, argv, args.output_dir, args.timeout)
    except (SystemExit, OSError, subprocess.SubprocessError) as exc:
        result = {"agent_name": args.role, "dispatchable": False, "status": "preflight_failed",
                  "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["dispatchable"] else 2)


if __name__ == "__main__":
    main()
