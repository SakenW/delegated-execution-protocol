#!/usr/bin/env python3
"""Select a GPT-5.6 delegated-agent profile from observable task properties."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KINDS = ("scan", "documentation", "implementation", "review", "planning-audit", "arbitration")
WRITES = ("none", "bounded", "broad")
SCOPES = ("small", "medium", "cross-module")
LEVELS = ("low", "medium", "high", "critical")
AMBIGUITIES = ("low", "medium", "high")
PARALLEL_VALUES = ("none", "useful", "critical-path")
TASK_SIZES = ("micro", "small", "medium", "large")
INDEPENDENT_EVIDENCE = ("none", "useful", "required")
PRIORITIES = ("economy", "balanced", "quality")
WORKLOADS = ("one-off", "batch")
VERIFICATIONS = ("weak", "normal", "strong")
SENSITIVITIES = ("none", "contract-sensitive")
COORDINATIONS = ("isolated", "steerable")
SHARDING_EVIDENCE = ("none", "measured-throughput", "critical-path")
ISOLATED_TRANSPORT_PREFERENCES = (
    "auto",
    "native-verified",
    "user-owned-desktop-task",
    "explicit-cli",
)
STEERING_TRIGGERS = (
    "none",
    "partial-results",
    "user-steering",
    "shared-session-state",
    "risk-cancellation",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--writes", choices=WRITES, required=True)
    parser.add_argument("--scope", choices=SCOPES, required=True)
    parser.add_argument("--risk", choices=LEVELS, required=True)
    parser.add_argument("--ambiguity", choices=AMBIGUITIES, required=True)
    parser.add_argument("--parallel-value", choices=PARALLEL_VALUES, required=True)
    parser.add_argument("--task-size", choices=TASK_SIZES, required=True)
    parser.add_argument(
        "--independent-evidence",
        choices=INDEPENDENT_EVIDENCE,
        required=True,
    )
    parser.add_argument("--batch-size", type=positive_int, default=1)
    parser.add_argument("--requested-workers", type=positive_int, default=1)
    parser.add_argument(
        "--sharding-evidence",
        choices=SHARDING_EVIDENCE,
        default="none",
    )
    parser.add_argument("--priority", choices=PRIORITIES, default="economy")
    parser.add_argument("--workload", choices=WORKLOADS, default="one-off")
    parser.add_argument("--verification", choices=VERIFICATIONS, default="normal")
    parser.add_argument("--sensitivity", choices=SENSITIVITIES, required=True)
    parser.add_argument("--coordination", choices=COORDINATIONS, default="isolated")
    parser.add_argument(
        "--transport-preference",
        choices=ISOLATED_TRANSPORT_PREFERENCES,
        default="auto",
    )
    parser.add_argument(
        "--steering-trigger",
        choices=STEERING_TRIGGERS,
        default="none",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path.home() / ".codex" / "models_cache.json",
    )
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def select(args: argparse.Namespace) -> dict[str, Any]:
    if args.coordination == "steerable" and args.steering_trigger == "none":
        raise SystemExit(
            "steerable coordination requires a concrete steering trigger: "
            "partial-results, user-steering, shared-session-state, or risk-cancellation"
        )
    if args.coordination == "isolated" and args.steering_trigger != "none":
        raise SystemExit("isolated coordination cannot declare a steering trigger")
    if args.coordination == "steerable" and args.transport_preference != "auto":
        raise SystemExit(
            "steerable coordination requires auto transport with a native named-agent; "
            "isolated transport preferences are not applicable"
        )
    if args.workload != "batch" and args.sharding_evidence != "none":
        raise SystemExit("sharding evidence is only valid for batch workloads")

    high_impact = args.risk in {"high", "critical"}
    high_ambiguity = args.ambiguity == "high"
    weak_verification = args.verification == "weak"
    contract_sensitive = args.sensitivity == "contract-sensitive"
    broad = args.scope == "cross-module" or args.writes == "broad"
    requested_priority = args.priority
    routing_warnings: list[str] = []
    if weak_verification:
        routing_warnings.append(
            "verification is weak: report evidence gaps and do not present conclusions as verified"
        )

    cost_gate = delegation_value_gate(args)
    if not cost_gate["justified"]:
        result: dict[str, Any] = {
            "delegate": False,
            "reason": cost_gate["reason"],
            "cost_gate": "rejected",
            "requested_priority": requested_priority,
            "effective_priority": "main",
            "routing_warnings": routing_warnings,
            "recommended_transport": "main-conversation",
            "transport_enforced": False,
            "transport_preference": args.transport_preference,
            "max_workers": 0,
            "bundle_required": False,
            "requested_workers": args.requested_workers,
            "sharding_evidence": args.sharding_evidence,
            "sharding_justified": False,
        }
        if args.kind in {"review", "planning-audit", "arbitration"} and args.writes != "none":
            result.update(
                {
                    "split_required": True,
                    "dispatchable": False,
                    "sequence": ["main-conversation-review", "main-conversation-execution"],
                }
            )
        return result

    worker_budget = worker_budget_for(args)

    if args.kind in {"review", "planning-audit", "arbitration"} and args.writes != "none":
        review_profile = review_profile_for(args)
        worker_profile = (
            ("delegated_senior_worker", "gpt-5.6-sol", "high")
            if high_impact or broad or weak_verification or contract_sensitive or requested_priority == "quality"
            else ("delegated_worker", "gpt-5.6-terra", "medium")
        )
        if requested_priority == "economy":
            routing_warnings.append(
                "economy ignored: review/write hybrids require a read-only review before execution"
            )
        steps = []
        for index, (agent_name, model, effort) in enumerate((review_profile, worker_profile)):
            logical_agent_name = agent_name
            recommended_transport = isolated_transport_for(args.transport_preference)
            resolved_model, resolved_effort, substitution = resolve_catalog(
                args.catalog, model, effort
            )
            steps.append(
                {
                    "delegate": True,
                    "requires_main_acceptance": index == 1,
                    "agent_name": agent_name,
                    "logical_agent_name": logical_agent_name,
                    "model": resolved_model,
                    "model_reasoning_effort": resolved_effort,
                    "catalog_substitution": substitution,
                    "recommended_transport": recommended_transport,
                    "transport_enforced": True,
                    "transport_preference": args.transport_preference,
                }
            )
        return {
            "delegate": False,
            "dispatchable": False,
            "split_required": True,
            "sequence": [step["logical_agent_name"] for step in steps],
            "steps": steps,
            "reason": "review and write work must be split into read-only review then bounded execution",
            "requested_priority": requested_priority,
            "effective_priority": (
                "quality"
                if requested_priority == "quality"
                else "balanced"
            ),
            "routing_warnings": routing_warnings,
            "recommended_transport": "sequential-per-step",
            "transport_enforced": True,
            "transport_preference": args.transport_preference,
            "cost_gate": "justified",
            **worker_budget,
        }

    if args.kind in {"planning-audit", "arbitration"} and high_impact and high_ambiguity:
        profile = ("delegated_planning_auditor", "gpt-5.6-sol", "xhigh")
        reason = "high-impact and high-ambiguity planning or arbitration"
        effective_priority = "quality"
    elif requested_priority == "quality":
        if args.writes == "none":
            profile = ("delegated_reviewer", "gpt-5.6-sol", "high")
            reason = "quality-priority read-only work"
        else:
            profile = ("delegated_senior_worker", "gpt-5.6-sol", "high")
            reason = "quality-priority execution"
        effective_priority = "quality"
    elif can_use_luna_read(args):
        profile = ("delegated_batch_explorer", "gpt-5.6-luna", "low")
        reason = "economy-priority repetitive read-only work"
        effective_priority = "economy"
    elif can_use_luna_write(args):
        profile = ("delegated_batch_worker", "gpt-5.6-luna", "medium")
        reason = "economy-priority repetitive bounded work with strong verification"
        effective_priority = "economy"
    else:
        if requested_priority == "economy":
            routing_warnings.append(luna_rejection_reason(args))
        effective_priority = "balanced"

        if args.writes == "none" and args.kind in {"review", "planning-audit", "arbitration"}:
            profile = review_profile_for(args)
            if profile[0] == "delegated_standard_reviewer":
                reason = "bounded low- or medium-risk review with verifiable evidence"
            else:
                reason = "high-impact, cross-module, weakly verified, or contract-sensitive review"
        elif args.writes == "none" and (high_impact or contract_sensitive):
            profile = ("delegated_reviewer", "gpt-5.6-sol", "high")
            reason = "high-impact or contract-sensitive read-only evidence collection"
        elif args.writes == "none" and weak_verification:
            profile = ("delegated_researcher", "gpt-5.6-terra", "medium")
            reason = "read-only evidence collection with explicit verification gaps"
        elif (
            args.writes == "none"
            and high_ambiguity
            and args.risk in {"low", "medium"}
            and args.verification in {"normal", "strong"}
        ):
            profile = ("delegated_deep_researcher", "gpt-5.6-terra", "high")
            reason = "high-ambiguity research with bounded risk and verifiable evidence"
        elif args.writes == "none" and (
            args.ambiguity == "medium" or args.scope == "cross-module"
        ):
            profile = ("delegated_researcher", "gpt-5.6-terra", "medium")
            reason = "multi-file or moderately ambiguous read-only research"
        elif args.writes == "none":
            profile = ("delegated_explorer", "gpt-5.6-terra", "low")
            reason = "bounded read-only evidence collection"
        elif high_impact or broad or weak_verification or contract_sensitive:
            profile = ("delegated_senior_worker", "gpt-5.6-sol", "high")
            reason = "high-risk, contract-sensitive, weakly verified, or cross-module execution"
        elif (
            args.writes == "bounded"
            and args.kind in {"documentation", "implementation"}
            and high_ambiguity
            and args.risk in {"low", "medium"}
            and args.verification == "strong"
        ):
            profile = ("delegated_complex_worker", "gpt-5.6-terra", "high")
            reason = "complex bounded execution protected by strong verification"
        else:
            profile = ("delegated_worker", "gpt-5.6-terra", "medium")
            reason = "ordinary bounded execution"

    agent_name, model, effort = profile
    requested_model = model
    model, effort, substitution = resolve_catalog(args.catalog, model, effort)
    if requested_model == "gpt-5.6-luna" and model != requested_model:
        if agent_name == "delegated_batch_explorer":
            agent_name = "delegated_explorer"
        elif agent_name == "delegated_batch_worker":
            agent_name = "delegated_worker"
        effective_priority = "balanced"
        routing_warnings.append(
            substitution or "Luna unavailable; used the matching balanced profile"
        )
    return {
        "delegate": True,
        "agent_name": agent_name,
        "model": model,
        "model_reasoning_effort": effort,
        "reason": reason,
        "catalog_substitution": substitution,
        "requested_priority": requested_priority,
        "effective_priority": effective_priority,
        "routing_warnings": routing_warnings,
        "recommended_transport": isolated_transport_for(args.transport_preference),
        "transport_enforced": True,
        "transport_preference": args.transport_preference,
        "cost_gate": "justified",
        **worker_budget,
    }


def delegation_value_gate(args: argparse.Namespace) -> dict[str, str | bool]:
    """Reject worker cold starts unless they buy evidence, isolation, or real throughput."""
    if args.independent_evidence == "required":
        return {"justified": True, "reason": "independent evidence is required"}
    if args.coordination == "steerable":
        return {"justified": True, "reason": "live steering requires a worker session"}
    if args.workload == "batch" and args.batch_size >= 10:
        return {"justified": True, "reason": "batch size amortizes worker cold-start cost"}
    if args.task_size in {"medium", "large"} and (
        args.parallel_value in {"useful", "critical-path"}
        or args.scope == "cross-module"
    ):
        return {"justified": True, "reason": "substantial work has real parallel or scope value"}
    if args.task_size == "large":
        return {"justified": True, "reason": "large bounded work amortizes worker cold-start cost"}
    return {
        "justified": False,
        "reason": "worker cold-start cost exceeds expected task value; keep work in the main conversation",
    }


def review_profile_for(args: argparse.Namespace) -> tuple[str, str, str]:
    """Use Terra for ordinary bounded review and reserve Sol for material review risk."""
    if (
        args.kind in {"planning-audit", "arbitration"}
        and args.risk in {"high", "critical"}
        and args.ambiguity == "high"
    ):
        return ("delegated_planning_auditor", "gpt-5.6-sol", "xhigh")
    if (
        args.risk in {"low", "medium"}
        and args.scope != "cross-module"
        and args.writes != "broad"
        and args.verification in {"normal", "strong"}
        and args.sensitivity == "none"
        and args.priority != "quality"
    ):
        return ("delegated_standard_reviewer", "gpt-5.6-terra", "high")
    return ("delegated_reviewer", "gpt-5.6-sol", "high")


def worker_budget_for(args: argparse.Namespace) -> dict[str, int | bool | str]:
    sharding_justified = (
        args.workload == "batch" and args.sharding_evidence != "none"
    )
    max_workers = 2 if args.workload != "batch" or sharding_justified else 1
    bundle_required = args.requested_workers > max_workers
    return {
        "max_workers": max_workers,
        "bundle_required": bundle_required,
        "requested_workers": args.requested_workers,
        "sharding_evidence": args.sharding_evidence,
        "sharding_justified": sharding_justified,
    }


def isolated_transport_for(preference: str) -> str:
    transports = {
        "auto": "native-named-agent",
        "native-verified": "native-named-agent",
        "user-owned-desktop-task": "user-owned-desktop-task",
        "explicit-cli": "explicit-codex-cli",
    }
    return transports[preference]


def can_use_luna_read(args: argparse.Namespace) -> bool:
    return (
        args.priority == "economy"
        and args.workload == "batch"
        and args.coordination == "isolated"
        and args.writes == "none"
        and args.risk == "low"
        and args.ambiguity == "low"
        and args.verification in {"normal", "strong"}
        and args.sensitivity == "none"
        and args.kind not in {"review", "planning-audit", "arbitration"}
    )


def can_use_luna_write(args: argparse.Namespace) -> bool:
    return (
        args.priority == "economy"
        and args.workload == "batch"
        and args.coordination == "isolated"
        and args.writes == "bounded"
        and args.scope != "cross-module"
        and args.risk == "low"
        and args.ambiguity == "low"
        and args.verification == "strong"
        and args.sensitivity == "none"
        and args.kind in {"documentation", "implementation"}
    )


def luna_rejection_reason(args: argparse.Namespace) -> str:
    failed: list[str] = []
    if args.workload != "batch":
        failed.append("workload is not batch")
    if args.coordination != "isolated":
        failed.append("coordination requires a steerable worker")
    if args.risk != "low":
        failed.append("risk is not low")
    if args.ambiguity != "low":
        failed.append("ambiguity is not low")
    if args.writes == "none" and args.verification == "weak":
        failed.append("read verification is weak")
    if args.kind in {"review", "planning-audit", "arbitration"}:
        failed.append("task requires judgment")
    if args.sensitivity != "none":
        failed.append("task is contract-sensitive")
    if args.writes == "broad" or (args.writes != "none" and args.scope == "cross-module"):
        failed.append("write scope is too broad")
    if args.writes != "none" and args.verification != "strong":
        failed.append("write verification is not strong")
    if args.writes != "none" and args.kind not in {"documentation", "implementation"}:
        failed.append("write kind is not a bounded execution kind")
    detail = ", ".join(failed) or "task does not satisfy the Luna safety gate"
    return f"economy fell back to balanced: {detail}"


def resolve_catalog(catalog_path: Path, preferred_model: str, effort: str) -> tuple[str, str, str | None]:
    if not catalog_path.is_file():
        raise SystemExit(f"model catalog unavailable: {catalog_path}")

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    models = data.get("models", [])
    supported: dict[str, set[str]] = {}
    for item in models:
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.startswith("gpt-5.6"):
            continue
        levels = item.get("supported_reasoning_levels", [])
        supported[slug] = {
            level["effort"]
            for level in levels
            if isinstance(level, dict) and isinstance(level.get("effort"), str)
        }

    if effort in supported.get(preferred_model, set()):
        return preferred_model, effort, None

    if preferred_model == "gpt-5.6-luna" and effort in supported.get("gpt-5.6-terra", set()):
        return (
            "gpt-5.6-terra",
            effort,
            f"{preferred_model} does not support {effort}; used the matching gpt-5.6-terra profile",
        )

    raise SystemExit(f"required profile unavailable: {preferred_model}/{effort}")


def main() -> None:
    print(json.dumps(select(parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
