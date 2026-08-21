#!/usr/bin/env python3
"""Behavior tests for delegated-agent profile selection."""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("select_agent_profile.py")


def load_selector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("select_agent_profile", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load selector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(catalog: Path, **overrides: str) -> argparse.Namespace:
    values = {
        "kind": "implementation",
        "writes": "bounded",
        "scope": "medium",
        "risk": "medium",
        "ambiguity": "low",
        "parallel_value": "useful",
        "task_size": "medium",
        "independent_evidence": "none",
        "batch_size": 1,
        "requested_workers": 1,
        "sharding_evidence": "none",
        "priority": "economy",
        "workload": "one-off",
        "verification": "normal",
        "sensitivity": "none",
        "coordination": "isolated",
        "transport_preference": "auto",
        "steering_trigger": "none",
        "catalog": catalog,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class SelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalog = Path(self.temp_dir.name) / "models_cache.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "slug": "gpt-5.6-sol",
                            "supported_reasoning_levels": [
                                {"effort": level}
                                for level in ("low", "medium", "high", "xhigh")
                            ],
                        },
                        {
                            "slug": "gpt-5.6-terra",
                            "supported_reasoning_levels": [
                                {"effort": level}
                                for level in ("low", "medium", "high")
                            ],
                        },
                        {
                            "slug": "gpt-5.6-luna",
                            "supported_reasoning_levels": [
                                {"effort": level}
                                for level in ("low", "medium", "high")
                            ],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_keeps_trivial_work_in_main_conversation(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                parallel_value="none",
            )
        )
        self.assertFalse(result["delegate"])

    def test_cli_defaults_to_economy_priority(self) -> None:
        with patch(
            "sys.argv",
            [
                str(SCRIPT_PATH),
                "--kind", "scan",
                "--writes", "none",
                "--scope", "medium",
                "--risk", "low",
                "--ambiguity", "low",
                "--parallel-value", "useful",
                "--task-size", "medium",
                "--independent-evidence", "none",
                "--sensitivity", "none",
            ],
        ):
            parsed = load_selector().parse_args()
        self.assertEqual(parsed.priority, "economy")

    def test_cli_requires_sensitivity(self) -> None:
        with patch(
            "sys.argv",
            [
                str(SCRIPT_PATH),
                "--kind", "scan", "--writes", "none", "--scope", "medium",
                "--risk", "low", "--ambiguity", "low", "--parallel-value", "useful",
                "--task-size", "medium", "--independent-evidence", "none",
            ],
        ):
            with self.assertRaises(SystemExit):
                load_selector().parse_args()

    def test_keeps_small_no_parallel_value_work_in_main_even_when_ambiguous(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="none",
                scope="small",
                risk="medium",
                ambiguity="medium",
                parallel_value="none",
            )
        )
        self.assertFalse(result["delegate"])

    def test_keeps_small_useful_parallel_scan_in_main_when_evidence_is_not_required(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                parallel_value="useful",
                task_size="small",
                independent_evidence="useful",
            )
        )
        self.assertFalse(result["delegate"])
        self.assertEqual(result["cost_gate"], "rejected")
        self.assertEqual(result["max_workers"], 0)

    def test_required_independent_evidence_uses_standard_reviewer_for_bounded_review(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="none",
                scope="small",
                risk="medium",
                ambiguity="medium",
                parallel_value="none",
                task_size="small",
                independent_evidence="required",
            )
        )
        self.assertTrue(result["delegate"])
        self.assertEqual(result["agent_name"], "delegated_standard_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "high")
        self.assertEqual(result["cost_gate"], "justified")

    def test_high_risk_small_execution_is_not_delegated_for_risk_alone(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="small",
                risk="high",
                ambiguity="low",
                parallel_value="none",
                task_size="small",
                independent_evidence="none",
            )
        )
        self.assertFalse(result["delegate"])
        self.assertEqual(result["cost_gate"], "rejected")

    def test_small_batch_below_amortization_threshold_stays_in_main(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                parallel_value="none",
                task_size="small",
                workload="batch",
                batch_size=9,
                priority="economy",
            )
        )
        self.assertFalse(result["delegate"])

    def test_batch_threshold_amortizes_cold_start_and_preserves_luna_route(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                parallel_value="none",
                task_size="small",
                workload="batch",
                batch_size=10,
                priority="economy",
            )
        )
        self.assertTrue(result["delegate"])
        self.assertEqual(result["agent_name"], "delegated_batch_explorer")
        self.assertEqual(result["max_workers"], 1)
        self.assertFalse(result["sharding_justified"])

    def test_batch_defaults_to_one_worker_and_bundles_extra_requests(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="low",
                workload="batch",
                batch_size=20,
                requested_workers=2,
            )
        )
        self.assertEqual(result["max_workers"], 1)
        self.assertTrue(result["bundle_required"])
        self.assertEqual(result["sharding_evidence"], "none")

    def test_measured_batch_throughput_justifies_two_workers(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="low",
                workload="batch",
                batch_size=20,
                requested_workers=2,
                sharding_evidence="measured-throughput",
            )
        )
        self.assertEqual(result["max_workers"], 2)
        self.assertFalse(result["bundle_required"])
        self.assertTrue(result["sharding_justified"])

    def test_critical_path_batch_evidence_justifies_at_most_two_workers(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="low",
                workload="batch",
                batch_size=20,
                requested_workers=3,
                sharding_evidence="critical-path",
            )
        )
        self.assertEqual(result["max_workers"], 2)
        self.assertTrue(result["bundle_required"])

    def test_sharding_evidence_is_rejected_for_one_off_work(self) -> None:
        with self.assertRaisesRegex(SystemExit, "only valid for batch"):
            load_selector().select(
                args(self.catalog, sharding_evidence="measured-throughput")
            )

    def test_more_than_two_requested_workers_requires_bundling(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="medium",
                parallel_value="useful",
                task_size="large",
                requested_workers=3,
            )
        )
        self.assertTrue(result["delegate"])
        self.assertEqual(result["max_workers"], 2)
        self.assertTrue(result["bundle_required"])

    def test_routes_read_only_scan_to_terra_low(self) -> None:
        result = load_selector().select(
            args(self.catalog, kind="scan", writes="none", scope="small", risk="low")
        )
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "low")

    def test_routes_bounded_implementation_to_terra_medium(self) -> None:
        result = load_selector().select(args(self.catalog))
        self.assertEqual(result["agent_name"], "delegated_worker")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "medium")

    def test_routes_economy_batch_read_only_to_luna_low(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
                verification="normal",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_batch_explorer")
        self.assertEqual(result["model"], "gpt-5.6-luna")
        self.assertEqual(result["model_reasoning_effort"], "low")

    def test_routes_economy_batch_write_with_strong_verification_to_luna_medium(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
                verification="strong",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_batch_worker")
        self.assertEqual(result["model"], "gpt-5.6-luna")
        self.assertEqual(result["model_reasoning_effort"], "medium")

    def test_economy_one_off_falls_back_to_balanced_terra(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="one-off",
                verification="strong",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_worker")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["effective_priority"], "balanced")
        self.assertTrue(result["routing_warnings"])

    def test_weak_verification_write_escalates_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="low",
                ambiguity="medium",
                priority="economy",
                workload="one-off",
                verification="weak",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_senior_worker")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_economy_batch_write_without_strong_verification_does_not_use_luna(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
                verification="weak",
            )
        )
        self.assertNotEqual(result["model"], "gpt-5.6-luna")
        self.assertEqual(result["effective_priority"], "balanced")

    def test_economy_batch_read_with_weak_verification_reports_gaps_on_terra(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
                batch_size=20,
                verification="weak",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_researcher")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "medium")
        self.assertTrue(any("read verification is weak" in item for item in result["routing_warnings"]))
        self.assertTrue(any("report evidence gaps" in item for item in result["routing_warnings"]))

    def test_economy_batch_requiring_steering_does_not_use_luna(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
                verification="normal",
                coordination="steerable",
                steering_trigger="partial-results",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "low")
        self.assertEqual(result["recommended_transport"], "native-named-agent")
        self.assertEqual(result["effective_priority"], "balanced")
        self.assertTrue(result["routing_warnings"])
        self.assertTrue(result["transport_enforced"])

    def test_steerable_coordination_requires_a_specific_trigger(self) -> None:
        with self.assertRaisesRegex(SystemExit, "steerable coordination requires"):
            load_selector().select(
                args(
                    self.catalog,
                    kind="scan",
                    writes="none",
                    scope="medium",
                    risk="low",
                    ambiguity="low",
                    coordination="steerable",
                    steering_trigger="none",
                )
            )

    def test_steerable_coordination_rejects_isolated_transport_preference(self) -> None:
        with self.assertRaisesRegex(SystemExit, "requires auto transport"):
            load_selector().select(
                args(
                    self.catalog,
                    coordination="steerable",
                    steering_trigger="partial-results",
                    transport_preference="explicit-cli",
                )
            )

    def test_isolated_route_uses_current_verified_native_transport(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                coordination="isolated",
            )
        )
        self.assertEqual(result["recommended_transport"], "native-named-agent")
        self.assertTrue(result["transport_enforced"])

    def test_isolated_transport_preferences_are_mapped_explicitly(self) -> None:
        expected = {
            "auto": "native-named-agent",
            "native-verified": "native-named-agent",
            "user-owned-desktop-task": "user-owned-desktop-task",
            "explicit-cli": "explicit-codex-cli",
        }
        for preference, transport in expected.items():
            with self.subTest(preference=preference):
                result = load_selector().select(
                    args(self.catalog, transport_preference=preference)
                )
                self.assertEqual(result["transport_preference"], preference)
                self.assertEqual(result["recommended_transport"], transport)

    def test_missing_luna_catalog_falls_back_to_matching_terra_profile(self) -> None:
        catalog = Path(self.temp_dir.name) / "models_without_luna.json"
        data = json.loads(self.catalog.read_text(encoding="utf-8"))
        data["models"] = [
            item for item in data["models"] if item["slug"] != "gpt-5.6-luna"
        ]
        catalog.write_text(json.dumps(data), encoding="utf-8")

        result = load_selector().select(
            args(
                catalog,
                kind="scan",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="economy",
                workload="batch",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["effective_priority"], "balanced")
        self.assertTrue(result["routing_warnings"])

    def test_missing_catalog_fails_closed(self) -> None:
        with self.assertRaises(SystemExit):
            load_selector().select(
                args(
                    Path(self.temp_dir.name) / "missing.json",
                    kind="scan",
                    writes="none",
                    scope="medium",
                    risk="low",
                    ambiguity="low",
                )
            )

    def test_luna_write_fallback_fails_when_terra_medium_is_unavailable(self) -> None:
        catalog = Path(self.temp_dir.name) / "no_luna_or_terra_medium.json"
        data = json.loads(self.catalog.read_text(encoding="utf-8"))
        data["models"] = [
            item for item in data["models"] if item["slug"] != "gpt-5.6-luna"
        ]
        for item in data["models"]:
            if item["slug"] == "gpt-5.6-terra":
                item["supported_reasoning_levels"] = [{"effort": "low"}]
        catalog.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(SystemExit):
            load_selector().select(
                args(
                    catalog,
                    kind="implementation",
                    writes="bounded",
                    scope="medium",
                    risk="low",
                    ambiguity="low",
                    priority="economy",
                    workload="batch",
                    verification="strong",
                )
            )

    def test_routes_balanced_medium_ambiguity_read_only_to_terra_medium(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="medium",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_researcher")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "medium")

    def test_routes_high_ambiguity_low_risk_research_to_terra_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="high",
                verification="strong",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_deep_researcher")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_strongly_verified_complex_bounded_write_to_terra_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="medium",
                ambiguity="high",
                verification="strong",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_complex_worker")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_quality_priority_routes_low_risk_read_only_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="low",
                priority="quality",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_serious_review_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="none",
                scope="cross-module",
                risk="high",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_bounded_low_risk_review_to_standard_reviewer(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="low",
                verification="strong",
                independent_evidence="required",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_standard_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_contract_sensitive_review_routes_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="none",
                scope="small",
                risk="low",
                ambiguity="low",
                verification="strong",
                sensitivity="contract-sensitive",
                independent_evidence="required",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_high_risk_read_only_scan_to_reviewer(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="high",
                ambiguity="medium",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_reviewer")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_requires_split_for_review_and_fix_hybrid(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="bounded",
                scope="medium",
                risk="medium",
                ambiguity="medium",
            )
        )
        self.assertFalse(result["delegate"])
        self.assertFalse(result["dispatchable"])
        self.assertTrue(result["split_required"])
        self.assertEqual(result["sequence"], ["delegated_standard_reviewer", "delegated_worker"])
        self.assertTrue(all(step["delegate"] for step in result["steps"]))
        self.assertFalse(result["steps"][0]["requires_main_acceptance"])
        self.assertTrue(result["steps"][1]["requires_main_acceptance"])

    def test_high_impact_high_ambiguity_review_fix_does_not_use_planning_auditor(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="review",
                writes="bounded",
                scope="medium",
                risk="high",
                ambiguity="high",
            )
        )
        self.assertTrue(result["split_required"])
        self.assertEqual(result["steps"][0]["logical_agent_name"], "delegated_reviewer")
        self.assertEqual(result["steps"][0]["model_reasoning_effort"], "high")

    def test_all_read_only_routes_use_read_only_profiles(self) -> None:
        read_only_profiles = {
            "delegated_batch_explorer",
            "delegated_explorer",
            "delegated_researcher",
            "delegated_deep_researcher",
            "delegated_standard_reviewer",
            "delegated_reviewer",
            "delegated_planning_auditor",
        }
        for kind in load_selector().KINDS:
            for scope in load_selector().SCOPES:
                for risk in load_selector().LEVELS:
                    for ambiguity in load_selector().AMBIGUITIES:
                        for parallel_value in load_selector().PARALLEL_VALUES:
                            with self.subTest(
                                kind=kind,
                                scope=scope,
                                risk=risk,
                                ambiguity=ambiguity,
                                parallel_value=parallel_value,
                            ):
                                result = load_selector().select(
                                    args(
                                        self.catalog,
                                        kind=kind,
                                        writes="none",
                                        scope=scope,
                                        risk=risk,
                                        ambiguity=ambiguity,
                                        parallel_value=parallel_value,
                                    )
                                )
                                if result["delegate"]:
                                    self.assertIn(result["agent_name"], read_only_profiles)

    def test_all_review_write_hybrids_require_split(self) -> None:
        for kind in ("review", "planning-audit", "arbitration"):
            for writes in ("bounded", "broad"):
                for scope in load_selector().SCOPES:
                    for risk in load_selector().LEVELS:
                        for ambiguity in load_selector().AMBIGUITIES:
                            for parallel_value in load_selector().PARALLEL_VALUES:
                                with self.subTest(
                                    kind=kind,
                                    writes=writes,
                                    scope=scope,
                                    risk=risk,
                                    ambiguity=ambiguity,
                                    parallel_value=parallel_value,
                                ):
                                    result = load_selector().select(
                                        args(
                                            self.catalog,
                                            kind=kind,
                                            writes=writes,
                                            scope=scope,
                                            risk=risk,
                                            ambiguity=ambiguity,
                                            parallel_value=parallel_value,
                                        )
                                    )
                                    self.assertTrue(result.get("split_required"))
                                    self.assertFalse(result.get("dispatchable"))
                                    for step in result.get("steps", []):
                                        self.assertTrue(step["delegate"])
                                    if result.get("steps"):
                                        self.assertTrue(
                                            result["steps"][-1]["requires_main_acceptance"]
                                        )

    def test_routes_high_risk_implementation_to_senior_worker(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="cross-module",
                risk="high",
                ambiguity="medium",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_senior_worker")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_non_xhigh_bounded_planning_audit_to_standard_reviewer(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="planning-audit",
                writes="none",
                scope="medium",
                risk="medium",
                ambiguity="medium",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_standard_reviewer")
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_uses_xhigh_only_for_high_impact_high_ambiguity_audit(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="planning-audit",
                writes="none",
                scope="cross-module",
                risk="critical",
                ambiguity="high",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_planning_auditor")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertEqual(result["model_reasoning_effort"], "xhigh")

    def test_exhaustive_routing_invariants(self) -> None:
        module = load_selector()
        module.resolve_catalog = lambda _path, model, effort: (model, effort, None)
        write_profiles = {
            "delegated_batch_worker",
            "delegated_worker",
            "delegated_complex_worker",
            "delegated_senior_worker",
        }
        violations: list[str] = []

        for values in itertools.product(
            module.KINDS,
            module.WRITES,
            module.SCOPES,
            module.LEVELS,
            module.AMBIGUITIES,
            module.PARALLEL_VALUES,
            module.PRIORITIES,
            module.WORKLOADS,
            module.VERIFICATIONS,
            module.SENSITIVITIES,
            module.COORDINATIONS,
        ):
            (
                kind,
                writes,
                scope,
                risk,
                ambiguity,
                parallel_value,
                priority,
                workload,
                verification,
                sensitivity,
                coordination,
            ) = values
            candidate = args(
                self.catalog,
                kind=kind,
                writes=writes,
                scope=scope,
                risk=risk,
                ambiguity=ambiguity,
                parallel_value=parallel_value,
                priority=priority,
                workload=workload,
                verification=verification,
                sensitivity=sensitivity,
                coordination=coordination,
                steering_trigger=(
                    "partial-results" if coordination == "steerable" else "none"
                ),
            )
            result = module.select(candidate)
            label = "/".join(values)

            if result.get("split_required"):
                if kind not in {"review", "planning-audit", "arbitration"} or writes == "none":
                    violations.append(f"invalid split: {label}")
                for step in result.get("steps", []):
                    if step["model_reasoning_effort"] == "xhigh" and not (
                        kind in {"planning-audit", "arbitration"}
                        and risk in {"high", "critical"}
                        and ambiguity == "high"
                    ):
                        violations.append(f"invalid split xhigh: {label}")
                continue
            if not result["delegate"]:
                continue

            agent = result["agent_name"]
            model = result["model"]
            effort = result["model_reasoning_effort"]
            if effort == "max":
                violations.append(f"max is outside the protocol: {label}")
            if writes == "none" and agent in write_profiles:
                violations.append(f"read-only got write profile: {label}")

            if model == "gpt-5.6-luna":
                luna_read = (
                    priority == "economy"
                    and workload == "batch"
                    and coordination == "isolated"
                    and writes == "none"
                    and risk == "low"
                    and ambiguity == "low"
                    and verification in {"normal", "strong"}
                    and sensitivity == "none"
                    and kind not in {"review", "planning-audit", "arbitration"}
                )
                luna_write = (
                    priority == "economy"
                    and workload == "batch"
                    and coordination == "isolated"
                    and writes == "bounded"
                    and scope != "cross-module"
                    and risk == "low"
                    and ambiguity == "low"
                    and verification == "strong"
                    and sensitivity == "none"
                    and kind in {"documentation", "implementation"}
                )
                if not (luna_read or luna_write) or effort not in {"low", "medium"}:
                    violations.append(f"unsafe Luna: {label}")

            if (
                module.can_use_luna_read(candidate)
                or module.can_use_luna_write(candidate)
            ) and model != "gpt-5.6-luna":
                violations.append(f"non-minimal route skipped Luna: {label}")

            if coordination == "steerable" and (
                result["recommended_transport"] != "native-named-agent"
                or result["transport_preference"] != "auto"
            ):
                violations.append(f"steerable transport mismatch: {label}")
            if priority == "quality" and coordination == "isolated" and model != "gpt-5.6-sol":
                violations.append(f"quality did not use Sol: {label}")

        self.assertEqual(violations[:10], [], f"routing invariant failures: {len(violations)}")


if __name__ == "__main__":
    unittest.main()
