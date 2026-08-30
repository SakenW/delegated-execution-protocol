#!/usr/bin/env python3
"""Negative tests for static/manual eval contract validation."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path(__file__).with_name("validate_protocol.py")


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_protocol", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load protocol validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StaticContractCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skill_root = Path(self.temp_dir.name)
        (self.skill_root / "policy.md").write_text(
            "required policy token\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_valid_file_token_contract_passes(self) -> None:
        count = load_validator().validate_static_contract_checks(
            self.skill_root,
            {
                "id": 900,
                "contract_checks": [
                    {
                        "path": "policy.md",
                        "required_tokens": ["required policy token"],
                    }
                ],
            },
        )
        self.assertEqual(count, 1)

    def test_missing_required_token_fails_closed(self) -> None:
        with self.assertRaisesRegex(SystemExit, "missing required token"):
            load_validator().validate_static_contract_checks(
                self.skill_root,
                {
                    "id": 901,
                    "contract_checks": [
                        {
                            "path": "policy.md",
                            "required_tokens": ["absent policy token"],
                        }
                    ],
                },
            )

    def test_parent_path_fails_closed(self) -> None:
        with self.assertRaisesRegex(SystemExit, "unsafe target path"):
            load_validator().validate_static_contract_checks(
                self.skill_root,
                {
                    "id": 902,
                    "contract_checks": [
                        {
                            "path": "../outside.md",
                            "required_tokens": ["anything"],
                        }
                    ],
                },
            )


if __name__ == "__main__":
    unittest.main()
