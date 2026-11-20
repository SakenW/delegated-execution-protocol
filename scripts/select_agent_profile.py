#!/usr/bin/env python3
"""Select a role from task properties, then resolve its configured model and permissions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_profiles import catalog_path, default_codex_home, load_binding, resolve_catalog


KINDS = ("scan", "documentation", "implementation", "computer-use", "review", "planning-audit", "arbitration")
WRITES = ("none", "bounded", "broad")
ALLOWED_WRITES_BY_KIND = {
    "scan": frozenset({"none"}),
    "documentation": frozenset(WRITES),
    "implementation": frozenset(WRITES),
    # Interactive navigation changes application state, even without editing files.
    "computer-use": frozenset({"bounded"}),
    "review": frozenset(WRITES),
    "planning-audit": frozenset(WRITES),
    "arbitration": frozenset(WRITES),
}
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
        default=None,
    )
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--native-binding", type=json.loads, action="append", default=[], help="Observed native binding JSON: agent_name, model, model_reasoning_effort, sandbox_mode, and model_provider when configured; repeat per role")
    parser.add_argument("--jev-shadow", action=argparse.BooleanOptionalAction,
                        default=os.environ.get("DELEGATION_JEV_SHADOW") == "1",
                        help="Observe ambiguous intent with Jev; never affects dispatch")
    parser.add_argument("--unclear-intent-summary", metavar="REDACTED_TEXT",
                        help="Supply a short, de-identified summary only when task intent is unclear")
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def select(args: argparse.Namespace) -> dict[str, Any]:
    if args.writes not in ALLOWED_WRITES_BY_KIND.get(args.kind, frozenset()):
        raise SystemExit(
            f"incompatible kind/writes combination: {args.kind} allows writes="
            + ",".join(sorted(ALLOWED_WRITES_BY_KIND.get(args.kind, ())))
        )
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
            "delegated_senior_worker"
            if high_impact or broad or weak_verification or contract_sensitive or requested_priority == "quality"
            else "delegated_worker"
        )
        if requested_priority == "economy":
            routing_warnings.append(
                "economy ignored: review/write hybrids require a read-only review before execution"
            )
        steps = []
        for index, role in enumerate((review_profile, worker_profile)):
            logical_agent_name = role
            binding, substitution = resolve_role(args, role)
            agent_name = binding["agent_name"]
            recommended_transport = transport_for(args, binding)
            steps.append(
                {
                    "delegate": True,
                    "requires_main_acceptance": index == 1,
                    "agent_name": agent_name,
                    "logical_agent_name": logical_agent_name,
                    **binding,
                    "catalog_substitution": substitution,
                    "recommended_transport": recommended_transport,
                    "transport_enforced": True,
                    "preflight_required": True,
                    "dispatchable": False,
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
            "preflight_required": True,
            "transport_preference": args.transport_preference,
            "cost_gate": "justified",
            **worker_budget,
        }

    if args.kind in {"planning-audit", "arbitration"} and high_impact and high_ambiguity:
        profile = "delegated_planning_auditor"
        reason = "high-impact and high-ambiguity planning or arbitration"
        effective_priority = "quality"
    elif requested_priority == "quality":
        if args.writes == "none":
            profile = "delegated_reviewer"
            reason = "quality-priority read-only work"
        else:
            profile = "delegated_senior_worker"
            reason = "quality-priority execution"
        effective_priority = "quality"
    elif args.kind == "computer-use":
        profile = (
            "delegated_senior_worker"
            if high_impact or broad or weak_verification or contract_sensitive or high_ambiguity
            else "delegated_computer_worker"
        )
        reason = "difficult computer workflow" if profile == "delegated_senior_worker" else "bounded visual computer operation"
        effective_priority = "balanced"
    elif can_use_batch_read(args):
        profile = "delegated_batch_explorer"
        reason = "economy-priority repetitive read-only work"
        effective_priority = "economy"
    elif can_use_batch_write(args):
        profile = "delegated_batch_worker"
        reason = "economy-priority repetitive bounded work with strong verification"
        effective_priority = "economy"
    else:
        if requested_priority == "economy":
            routing_warnings.append(batch_rejection_reason(args))
        effective_priority = "balanced"

        if args.writes == "none" and args.kind in {"review", "planning-audit", "arbitration"}:
            profile = review_profile_for(args)
            if profile == "delegated_standard_reviewer":
                reason = "bounded low- or medium-risk review with verifiable evidence"
            else:
                reason = "high-impact, cross-module, weakly verified, or contract-sensitive review"
        elif args.writes == "none" and (high_impact or contract_sensitive):
            profile = "delegated_reviewer"
            reason = "high-impact or contract-sensitive read-only evidence collection"
        elif args.writes == "none" and weak_verification:
            profile = "delegated_researcher"
            reason = "read-only evidence collection with explicit verification gaps"
        elif (
            args.writes == "none"
            and high_ambiguity
            and args.risk in {"low", "medium"}
            and args.verification in {"normal", "strong"}
        ):
            profile = "delegated_deep_researcher"
            reason = "high-ambiguity research with bounded risk and verifiable evidence"
        elif args.writes == "none" and (
            args.ambiguity == "medium" or args.scope == "cross-module"
            or args.risk != "low" or args.coordination != "isolated"
        ):
            profile = "delegated_researcher"
            reason = "multi-file, moderate-risk, steerable, or moderately ambiguous read-only research"
        elif args.writes == "none":
            profile = "delegated_explorer"
            reason = "bounded read-only evidence collection"
        elif high_impact or broad or weak_verification or contract_sensitive:
            profile = "delegated_senior_worker"
            reason = "high-risk, contract-sensitive, weakly verified, or cross-module execution"
        elif (
            args.writes == "bounded"
            and args.kind in {"documentation", "implementation"}
            and high_ambiguity
            and args.risk in {"low", "medium"}
            and args.verification == "strong"
        ):
            profile = "delegated_complex_worker"
            reason = "complex bounded execution protected by strong verification"
        else:
            profile = "delegated_worker"
            reason = "ordinary bounded execution"

    binding, substitution = resolve_role(args, profile)
    agent_name = binding["agent_name"]
    if substitution:
        effective_priority = "balanced"
        routing_warnings.append(substitution)
    return {
        "delegate": True,
        "agent_name": agent_name,
        **binding,
        "reason": reason,
        "catalog_substitution": substitution,
        "requested_priority": requested_priority,
        "effective_priority": effective_priority,
        "routing_warnings": routing_warnings,
        "recommended_transport": transport_for(args, binding),
        "transport_enforced": True,
        "preflight_required": True,
        "dispatchable": False,
        "transport_preference": args.transport_preference,
        "cost_gate": "justified",
        "required_capabilities": ["computer-use", "target-app-access"] if args.kind == "computer-use" else [],
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


def review_profile_for(args: argparse.Namespace) -> str:
    """Choose review responsibility independently of the configured model."""
    if (
        args.kind in {"planning-audit", "arbitration"}
        and args.risk in {"high", "critical"}
        and args.ambiguity == "high"
    ):
        return "delegated_planning_auditor"
    if (
        args.risk in {"low", "medium"}
        and args.scope != "cross-module"
        and args.writes != "broad"
        and args.verification in {"normal", "strong"}
        and args.sensitivity == "none"
        and args.priority != "quality"
    ):
        return "delegated_standard_reviewer"
    return "delegated_reviewer"


def worker_budget_for(args: argparse.Namespace) -> dict[str, int | bool | str]:
    sharding_justified = (
        args.workload == "batch" and args.sharding_evidence != "none"
    )
    max_workers = 2 if args.workload != "batch" or sharding_justified else 1
    if args.kind == "computer-use":
        # One task owns its app/tab session; do not shard shared UI state.
        max_workers = 1
        sharding_justified = False
    bundle_required = args.requested_workers > max_workers
    return {
        "max_workers": max_workers,
        "bundle_required": bundle_required,
        "requested_workers": args.requested_workers,
        "sharding_evidence": args.sharding_evidence,
        "sharding_justified": sharding_justified,
    }


def transport_for(args: argparse.Namespace, binding: dict[str, str]) -> str:
    role = binding["agent_name"]
    observed = getattr(args, "native_binding", [])
    if not isinstance(observed, list) or any(not isinstance(x, dict) for x in observed):
        raise SystemExit("native bindings must be JSON objects")
    matches = [x for x in observed if x.get("agent_name") == role]
    if len(matches) > 1:
        raise SystemExit(f"duplicate native binding evidence: {role}")
    required_fields = ["model", "model_reasoning_effort", "sandbox_mode"]
    if "model_provider" in binding:
        required_fields.append("model_provider")
    verified = bool(matches) and all(matches[0].get(key) == binding[key] for key in required_fields)
    if args.coordination == "steerable" and not verified:
        raise SystemExit(f"steerable role has no matching native model/effort/permission evidence (including configured provider): {role}")
    if args.transport_preference == "native-verified":
        if not verified:
            raise SystemExit(f"native binding does not match configured model/effort/permissions or provider: {role}")
        return "native-named-agent"
    if args.transport_preference == "auto":
        if verified:
            return "native-named-agent"
        return "explicit-codex-app-server" if args.kind == "computer-use" else "explicit-codex-cli"
    if args.transport_preference == "explicit-cli":
        return "explicit-codex-app-server" if args.kind == "computer-use" else "explicit-codex-cli"
    return "user-owned-desktop-task"


def resolve_role(args: argparse.Namespace, role: str) -> tuple[dict[str, str], str | None]:
    home = getattr(args, "codex_home", None) or default_codex_home()
    binding = load_binding(home, role)
    path = catalog_path(home, getattr(args, "catalog", None))
    # Catalog absence/unavailability is a blocker, never permission to change role/model.
    resolve_catalog(path, binding["model"], binding["model_reasoning_effort"])
    return binding, None


def can_use_batch_read(args: argparse.Namespace) -> bool:
    return (
        args.priority == "economy"
        and args.workload == "batch"
        and args.batch_size >= 10
        and args.coordination == "isolated"
        and args.writes == "none"
        and args.risk == "low"
        and args.ambiguity == "low"
        and args.verification in {"normal", "strong"}
        and args.sensitivity == "none"
        and args.kind not in {"review", "planning-audit", "arbitration"}
    )


def can_use_batch_write(args: argparse.Namespace) -> bool:
    return (
        args.priority == "economy"
        and args.workload == "batch"
        and args.batch_size >= 10
        and args.coordination == "isolated"
        and args.writes == "bounded"
        and args.scope != "cross-module"
        and args.risk == "low"
        and args.ambiguity == "low"
        and args.verification == "strong"
        and args.sensitivity == "none"
        and args.kind in {"documentation", "implementation"}
    )


def batch_rejection_reason(args: argparse.Namespace) -> str:
    failed: list[str] = []
    if args.workload != "batch":
        failed.append("workload is not batch")
    elif args.batch_size < 10:
        failed.append("batch size is below 10")
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
    detail = ", ".join(failed) or "task does not satisfy the batch safety gate"
    return f"economy fell back to balanced: {detail}"


def main() -> None:
    args = parse_args()
    observation = None
    if args.jev_shadow and args.unclear_intent_summary is not None:
        from jev_shadow import observe_intent
        observation = observe_intent(args.unclear_intent_summary)
    result = select(args)
    if observation is not None:
        result["jev_shadow"] = observation
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
