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

from test_profile_fixtures import TEST_BINDINGS, binding, write_profiles


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
        "codex_home": catalog.parent,
        "native_binding": [binding(catalog.parent, role) for role in TEST_BINDINGS],
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
                            "slug": "gpt-6.1-terra",
                            "supported_reasoning_levels": [{"effort": "medium"}],
                        },
                        {
                            "slug": "gpt-6.2-astra",
                            "supported_reasoning_levels": [
                                {"effort": level}
                                for level in ("low", "medium", "high", "xhigh")
                            ],
                        },
                        {
                            "slug": "gpt-6.2-sol",
                            "supported_reasoning_levels": [
                                {"effort": level}
                                for level in ("low", "medium", "high")
                            ],
                        },
                        {
                            "slug": "gpt-6-luna",
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

        write_profiles(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_bounded_computer_task_uses_terra_and_one_session(self) -> None:
        result = load_selector().select(args(self.catalog, kind="computer-use", requested_workers=2))
        self.assertEqual(result["agent_name"], "delegated_computer_worker")
        self.assertEqual(result["model"], "gpt-6.1-terra")
        self.assertEqual(result["model_reasoning_effort"], "medium")
        self.assertEqual(result["max_workers"], 1)
        self.assertTrue(result["bundle_required"])
        self.assertFalse(result["dispatchable"])
        self.assertEqual(result["required_capabilities"], ["computer-use", "target-app-access"])

    def test_computer_task_keeps_risk_and_small_task_gates(self) -> None:
        for override in ({"risk": "high"}, {"ambiguity": "high"}, {"verification": "weak"},
                         {"sensitivity": "contract-sensitive"}, {"scope": "cross-module"}, {"priority": "quality"}):
            with self.subTest(override=override):
                result = load_selector().select(args(self.catalog, kind="computer-use", **override))
                self.assertEqual(result["agent_name"], "delegated_senior_worker")
                self.assertEqual(result["max_workers"], 1)
        result = load_selector().select(args(self.catalog, kind="computer-use", task_size="small", parallel_value="none"))
        self.assertFalse(result["delegate"])

    def test_computer_use_does_not_claim_read_only_or_batch_luna(self) -> None:
        with self.assertRaisesRegex(SystemExit, "incompatible kind/writes"):
            load_selector().select(args(self.catalog, kind="computer-use", writes="none"))
        result = load_selector().select(args(self.catalog, kind="computer-use", risk="low", verification="strong",
                                            workload="batch", batch_size=20, sharding_evidence="measured-throughput"))
        self.assertEqual(result["agent_name"], "delegated_computer_worker")
        self.assertEqual(result["max_workers"], 1)
        self.assertFalse(result["sharding_justified"])

    def test_missing_terra_fails_without_model_substitution(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["models"] = [m for m in data["models"] if m["slug"] != "gpt-6.1-terra"]
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable"):
            load_selector().select(args(self.catalog, kind="computer-use"))

    def test_computer_task_uses_approval_capable_fallback(self) -> None:
        result = load_selector().select(args(self.catalog, kind="computer-use", native_binding=[]))
        self.assertEqual(result["recommended_transport"], "explicit-codex-app-server")
        result = load_selector().select(args(self.catalog, kind="computer-use", transport_preference="explicit-cli"))
        self.assertEqual(result["recommended_transport"], "explicit-codex-app-server")

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
        self.assertEqual(result["model"], "gpt-6.2-sol")
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

    def test_batch_size_one_uses_focused_explorer_not_batch(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="medium",
                risk="low",
                ambiguity="low",
                parallel_value="useful",
                task_size="medium",
                workload="batch",
                batch_size=1,
                priority="economy",
            )
        )
        self.assertTrue(result["delegate"])
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-6-luna")
        self.assertTrue(any("below 10" in item for item in result["routing_warnings"]))

    def test_batch_size_nine_uses_focused_explorer_not_batch(self) -> None:
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
                independent_evidence="required",
                workload="batch",
                batch_size=9,
                priority="economy",
            )
        )
        self.assertTrue(result["delegate"])
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-6-luna")
        self.assertTrue(any("below 10" in item for item in result["routing_warnings"]))

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

    def test_routes_read_only_scan_to_luna_high(self) -> None:
        result = load_selector().select(
            args(self.catalog, kind="scan", writes="none", scope="small", risk="low")
        )
        self.assertEqual(result["agent_name"], "delegated_explorer")
        self.assertEqual(result["model"], "gpt-6-luna")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_bounded_implementation_to_sol_medium(self) -> None:
        result = load_selector().select(args(self.catalog))
        self.assertEqual(result["agent_name"], "delegated_worker")
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "medium")

    def test_routes_economy_batch_read_only_to_luna_high(self) -> None:
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
                batch_size=10,
                verification="normal",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_batch_explorer")
        self.assertEqual(result["model"], "gpt-6-luna")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_economy_batch_write_with_strong_verification_to_luna_high(self) -> None:
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
                batch_size=10,
                verification="strong",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_batch_worker")
        self.assertEqual(result["model"], "gpt-6-luna")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_economy_one_off_falls_back_to_balanced_sol(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["effective_priority"], "balanced")
        self.assertTrue(result["routing_warnings"])

    def test_weak_verification_write_escalates_to_astra_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
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
                batch_size=10,
                verification="weak",
            )
        )
        self.assertNotEqual(result["model"], "gpt-6-luna")
        self.assertEqual(result["effective_priority"], "balanced")

    def test_economy_batch_read_with_weak_verification_reports_gaps_on_sol(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
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
                batch_size=10,
                verification="normal",
                coordination="steerable",
                steering_trigger="partial-results",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_researcher")
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "medium")
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

    def test_missing_luna_catalog_never_switches_model(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["models"] = [x for x in data["models"] if x["slug"] != "gpt-6-luna"]
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable: gpt-6-luna/high"):
            load_selector().select(args(self.catalog, kind="scan", writes="none",
                                       scope="medium", risk="low", ambiguity="low",
                                       workload="batch", batch_size=10))

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

    def test_missing_luna_write_fails_without_using_sol(self) -> None:
        catalog = Path(self.temp_dir.name) / "no_luna_or_sol_medium.json"
        data = json.loads(self.catalog.read_text(encoding="utf-8"))
        data["models"] = [
            item for item in data["models"] if item["slug"] != "gpt-6-luna"
        ]
        for item in data["models"]:
            if item["slug"] == "gpt-6.2-sol":
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
                    batch_size=10,
                    verification="strong",
                )
            )

    def test_routes_balanced_medium_ambiguity_read_only_to_sol_medium(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "medium")

    def test_routes_high_ambiguity_low_risk_research_to_sol_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_steerable_high_ambiguity_research_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="scan",
                writes="none",
                scope="cross-module",
                risk="low",
                ambiguity="high",
                verification="strong",
                coordination="steerable",
                steering_trigger="partial-results",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_deep_researcher")
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")
        self.assertEqual(result["recommended_transport"], "native-named-agent")

    def test_routes_strongly_verified_complex_bounded_write_to_sol_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_steerable_complex_bounded_write_to_sol_high(self) -> None:
        result = load_selector().select(
            args(
                self.catalog,
                kind="implementation",
                writes="bounded",
                scope="medium",
                risk="medium",
                ambiguity="high",
                verification="strong",
                coordination="steerable",
                steering_trigger="risk-cancellation",
            )
        )
        self.assertEqual(result["agent_name"], "delegated_complex_worker")
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")
        self.assertEqual(result["recommended_transport"], "native-named-agent")

    def test_kind_write_compatibility_fails_closed(self) -> None:
        for writes in ("bounded", "broad"):
            with self.subTest(kind="scan", writes=writes):
                with self.assertRaisesRegex(SystemExit, "incompatible kind/writes"):
                    load_selector().select(
                        args(self.catalog, kind="scan", writes=writes)
                    )

    def test_documentation_implementation_and_review_write_contracts(self) -> None:
        for kind in ("documentation", "implementation"):
            for writes in load_selector().WRITES:
                with self.subTest(kind=kind, writes=writes):
                    result = load_selector().select(
                        args(self.catalog, kind=kind, writes=writes)
                    )
                    self.assertFalse(result["dispatchable"])
                    self.assertTrue(result["preflight_required"])
        for kind in ("review", "planning-audit", "arbitration"):
            result = load_selector().select(
                args(self.catalog, kind=kind, writes="none")
            )
            self.assertNotIn("split_required", result)
            for writes in ("bounded", "broad"):
                with self.subTest(kind=kind, writes=writes):
                    result = load_selector().select(
                        args(self.catalog, kind=kind, writes=writes)
                    )
                    self.assertTrue(result["split_required"])
                    self.assertFalse(result["dispatchable"])

    def test_quality_priority_routes_low_risk_read_only_to_astra_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_routes_serious_review_to_astra_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
        self.assertEqual(result["model_reasoning_effort"], "high")

    def test_contract_sensitive_review_routes_to_astra_high(self) -> None:
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
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
            if "none" not in load_selector().ALLOWED_WRITES_BY_KIND[kind]:
                continue
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
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
        self.assertEqual(result["model"], "gpt-6.2-sol")
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
        self.assertEqual(result["model"], "gpt-6.2-astra")
        self.assertEqual(result["model_reasoning_effort"], "xhigh")

    def test_model_and_effort_come_from_role_config_for_any_provider(self) -> None:
        profile = Path(self.temp_dir.name) / "agents/delegated_reviewer.toml"
        profile.write_text(profile.read_text().replace('gpt-6.2-astra', 'vendor/custom-review').replace('"high"', '"medium"'))
        data = json.loads(self.catalog.read_text())
        data["models"].append({"slug": "vendor/custom-review", "supported_reasoning_levels": [{"effort": "medium"}]})
        self.catalog.write_text(json.dumps(data))
        result = load_selector().select(args(self.catalog, kind="review", writes="none", risk="high"))
        self.assertEqual((result["model"], result["model_reasoning_effort"]), ("vendor/custom-review", "medium"))
        self.assertEqual(result["sandbox_mode"], "read-only")

    def test_codex_home_and_configured_catalog_are_respected(self) -> None:
        home = Path(self.temp_dir.name)
        special = home / "custom-models.json"
        special.write_bytes(self.catalog.read_bytes())
        self.catalog.unlink()
        (home / "config.toml").write_text('model_catalog_json = "custom-models.json"\n')
        with patch.dict("os.environ", {"CODEX_HOME": str(home)}):
            candidate = args(self.catalog, codex_home=None)
            candidate.catalog = None
            result = load_selector().select(candidate)
        self.assertEqual(result["agent_name"], "delegated_worker")

    def test_registered_config_file_overrides_standalone_path(self) -> None:
        home = Path(self.temp_dir.name)
        original = home / "agents/delegated_worker.toml"
        alternate = home / "worker-profile.toml"
        alternate.write_bytes(original.read_bytes())
        original.unlink()
        (home / "config.toml").write_text('[agents.delegated_worker]\nconfig_file = "worker-profile.toml"\n')
        result = load_selector().select(args(self.catalog))
        self.assertEqual(result["config_file"], str(alternate.resolve()))

    def test_missing_astra_does_not_silently_fall_back_to_sol(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["models"] = [x for x in data["models"] if x["slug"] != "gpt-6.2-astra"]
        data["models"].append({"slug": "gpt-5.6-sol", "supported_reasoning_levels": [{"effort": "high"}]})
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable: gpt-6.2-astra/high"):
            load_selector().select(args(self.catalog, kind="review", writes="none", risk="high"))

    def test_unavailable_effort_fails_closed(self) -> None:
        profile = Path(self.temp_dir.name) / "agents/delegated_worker.toml"
        profile.write_text(profile.read_text().replace('"medium"', '"unavailable"'))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable"):
            load_selector().select(args(self.catalog))

    def test_read_only_profile_cannot_broaden_permissions(self) -> None:
        profile = Path(self.temp_dir.name) / "agents/delegated_reviewer.toml"
        profile.write_text(profile.read_text().replace('"read-only"', '"workspace-write"'))
        with self.assertRaisesRegex(SystemExit, "unsafe sandbox"):
            load_selector().select(args(self.catalog, kind="review", writes="none", risk="high"))

    def test_missing_profile_is_not_replaced_by_parent_defaults(self) -> None:
        (Path(self.temp_dir.name) / "agents/delegated_worker.toml").unlink()
        with self.assertRaisesRegex(SystemExit, "cannot read configuration"):
            load_selector().select(args(self.catalog))

    def test_auto_uses_cli_until_native_binding_is_verified(self) -> None:
        result = load_selector().select(args(self.catalog, native_binding=[]))
        self.assertEqual(result["recommended_transport"], "explicit-codex-cli")

    def test_explicit_native_and_steerable_need_current_evidence(self) -> None:
        for overrides in [
            {"transport_preference": "native-verified"},
            {"coordination": "steerable", "steering_trigger": "partial-results"},
        ]:
            with self.subTest(overrides=overrides), self.assertRaises(SystemExit):
                load_selector().select(args(self.catalog, native_binding=[], **overrides))

    def test_explicit_provider_matches_runtime_evidence(self) -> None:
        home = self.catalog.parent
        role = "delegated_reviewer"
        evidence = binding(home, role)
        (home / "config.toml").write_text('model_provider = "site"\n')
        selector = load_selector()
        for configured in ("site", "role-override"):
            if configured == "role-override":
                with (home / "agents" / f"{role}.toml").open("a") as profile:
                    profile.write('model_provider = "role-override"\n')
            for observed in (None, "other", "site", "role-override"):
                with self.subTest(configured=configured, observed=observed):
                    record = dict(evidence)
                    if observed is not None:
                        record["model_provider"] = observed
                    task = args(self.catalog, kind="review", writes="none", risk="high",
                                native_binding=[record])
                    matched = observed == configured
                    self.assertEqual(selector.select(task)["recommended_transport"],
                                     "native-named-agent" if matched else "explicit-codex-cli")
                    if not matched:
                        task.transport_preference = "native-verified"
                        with self.assertRaises(SystemExit):
                            selector.select(task)
                        task.transport_preference = "auto"
                        task.coordination = "steerable"
                        task.steering_trigger = "partial-results"
                        with self.assertRaises(SystemExit):
                            selector.select(task)

    def test_native_permission_mismatch_falls_back_to_read_only_cli(self) -> None:
        evidence = binding(Path(self.temp_dir.name), "delegated_reviewer")
        evidence["sandbox_mode"] = "workspace-write"
        result = load_selector().select(args(self.catalog, kind="review", writes="none", risk="high", native_binding=[evidence]))
        self.assertEqual(result["sandbox_mode"], "read-only")
        self.assertEqual(result["recommended_transport"], "explicit-codex-cli")

    def test_stale_native_model_or_effort_does_not_count_as_binding(self) -> None:
        for key, value in [("model", "gpt-5.6-sol"), ("model_reasoning_effort", "low")]:
            evidence = binding(Path(self.temp_dir.name), "delegated_reviewer")
            evidence[key] = value
            with self.subTest(key=key):
                result = load_selector().select(args(self.catalog, kind="review", writes="none", risk="high", native_binding=[evidence]))
                self.assertEqual(result["recommended_transport"], "explicit-codex-cli")


    def test_medium_risk_scan_does_not_use_focused_luna(self) -> None:
        result = load_selector().select(args(self.catalog, kind="scan", writes="none",
                                             scope="small", risk="medium"))
        self.assertEqual(result["agent_name"], "delegated_researcher")
        self.assertEqual(result["model"], "gpt-6.2-sol")

    def test_missing_focused_luna_does_not_use_sol_researcher(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["models"] = [x for x in data["models"] if x["slug"] != "gpt-6-luna"]
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable: gpt-6-luna/high"):
            load_selector().select(args(self.catalog, kind="scan", writes="none",
                                       scope="small", risk="low"))

    def test_missing_sol_does_not_revert_to_legacy_model(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["models"] = [x for x in data["models"] if x["slug"] != "gpt-6.2-sol"]
        data["models"].append({"slug": "gpt-6-sol",
                              "supported_reasoning_levels": [{"effort": "medium"}]})
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(SystemExit, "required profile unavailable: gpt-6.2-sol/medium"):
            load_selector().select(args(self.catalog))

    def test_exhaustive_routing_invariants(self) -> None:
        module = load_selector()
        module.resolve_catalog = lambda _path, model, effort: (model, effort, None)
        module.load_binding = binding
        module.catalog_path = lambda _home, explicit: explicit
        write_profiles = {
            "delegated_batch_worker",
            "delegated_worker",
            "delegated_complex_worker",
            "delegated_senior_worker",
            "delegated_computer_worker",
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
            label = "/".join(values)
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
            try:
                result = module.select(candidate)
            except SystemExit as exc:
                if writes not in module.ALLOWED_WRITES_BY_KIND[kind]:
                    continue
                violations.append(f"unexpected rejection: {label}: {exc}")
                continue

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

            if model == "gpt-6-luna":
                luna_read = (
                    priority == "economy"
                    and workload == "batch"
                    and candidate.batch_size >= 10
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
                    and candidate.batch_size >= 10
                    and coordination == "isolated"
                    and writes == "bounded"
                    and scope != "cross-module"
                    and risk == "low"
                    and ambiguity == "low"
                    and verification == "strong"
                    and sensitivity == "none"
                    and kind in {"documentation", "implementation"}
                )
                luna_focused_read = (
                    agent == "delegated_explorer"
                    and writes == "none"
                    and scope != "cross-module"
                    and risk == "low"
                    and ambiguity == "low"
                    and verification in {"normal", "strong"}
                    and sensitivity == "none"
                    and coordination == "isolated"
                    and priority != "quality"
                    and kind not in {"review", "planning-audit", "arbitration"}
                )
                if not (luna_read or luna_write or luna_focused_read) or effort != "high":
                    violations.append(f"unsafe Luna: {label}")

            if (
                module.can_use_batch_read(candidate)
                or module.can_use_batch_write(candidate)
            ) and model != "gpt-6-luna":
                violations.append(f"non-minimal route skipped Luna: {label}")

            if coordination == "steerable" and (
                result["recommended_transport"] != "native-named-agent"
                or result["transport_preference"] != "auto"
            ):
                violations.append(f"steerable transport mismatch: {label}")
            if priority == "quality" and coordination == "isolated" and model != "gpt-6.2-astra":
                violations.append(f"quality did not use configured high-capability role: {label}")

        self.assertEqual(violations[:10], [], f"routing invariant failures: {len(violations)}")


if __name__ == "__main__":
    unittest.main()
