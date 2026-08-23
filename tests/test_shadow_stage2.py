from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from run_shadow_eval import load_suite, run_suite  # noqa: E402


class Stage2SuiteTests(unittest.TestCase):
    def test_loader_accepts_five_stage2_ids(self) -> None:
        suite = load_suite(Path(__file__).parents[1] / "evals" / "shadow-stage2" / "suite.json")
        self.assertEqual(
            [case["id"] for case in suite["cases"]],
            [
                "stage2-helped",
                "stage2-harmed",
                "stage2-wasted-noop",
                "stage2-wasted-still-wrong",
                "stage2-skip-good",
            ],
        )

    def test_offline_stage2_pack_matches_all_labels(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-stage2" / "suite.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_suite(
                suite_path,
                output_root=Path(temp_dir) / "runs",
                report_path=Path(temp_dir) / "report.json",
                offline=True,
            )

        self.assertTrue(report["all_matched"])
        self.assertEqual(report["matched"], 5)
        self.assertEqual(report["stage2_outcomes"]["HELPED"], 1)
        self.assertEqual(report["stage2_outcomes"]["HARMED"], 1)
        self.assertEqual(report["stage2_outcomes"]["WASTED"], 2)
        self.assertEqual(report["stage2_outcomes"]["NONE"], 1)
        by_id = {item["id"]: item for item in report["cases"]}
        self.assertTrue(by_id["stage2-helped"]["repair_invoked"])
        self.assertFalse(by_id["stage2-helped"]["rollback_used"])
        self.assertNotEqual(by_id["stage2-helped"]["initial_hash"], by_id["stage2-helped"]["final_hash"])
        self.assertTrue(by_id["stage2-harmed"]["rollback_used"])
        self.assertFalse(by_id["stage2-skip-good"]["repair_invoked"])


if __name__ == "__main__":
    unittest.main()
