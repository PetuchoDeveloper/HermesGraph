from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from apply_eval_candidate import CandidateError, apply_candidate  # noqa: E402
from run_shadow_eval import (  # noqa: E402
    ScriptedVerifier,
    load_suite,
    main,
    materialize_case,
    run_case,
    run_suite,
)


class CandidateApplierTests(unittest.TestCase):
    def test_apply_candidate_copies_files_into_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "candidate"
            destination = root / "repo"
            (candidate / "nested").mkdir(parents=True)
            destination.mkdir()
            (candidate / "slug.py").write_text("return 'slug'\n", encoding="utf-8")
            (candidate / "nested" / "helper.py").write_text("HELPER = True\n", encoding="utf-8")

            copied = apply_candidate(candidate, destination)

            self.assertEqual(copied, ["nested/helper.py", "slug.py"])
            self.assertEqual((destination / "slug.py").read_text(encoding="utf-8"), "return 'slug'\n")
            self.assertEqual(
                (destination / "nested" / "helper.py").read_text(encoding="utf-8"),
                "HELPER = True\n",
            )

    def test_apply_candidate_refuses_dotenv_and_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "candidate"
            destination = root / "repo"
            candidate.mkdir()
            destination.mkdir()

            with self.assertRaisesRegex(CandidateError, r"\.env"):
                apply_candidate(root / ".." / ".env", destination)

            (candidate / "safe.txt").write_text("safe\n", encoding="utf-8")
            with self.assertRaisesRegex(CandidateError, "traversal"):
                apply_candidate(candidate, destination, relative_paths=["../escape.txt"])


class LoaderTests(unittest.TestCase):
    def test_loader_rejects_unknown_ground_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "cases" / "bad").mkdir(parents=True)
            (root / "suite.json").write_text(
                json.dumps({"suite_id": "test", "cases": ["cases/bad/case.json"]}),
                encoding="utf-8",
            )
            (root / "cases" / "bad" / "case.json").write_text(
                json.dumps(
                    {
                        "id": "bad",
                        "family": "slugify",
                        "ground_truth": "unknown",
                        "expected_policy": "accept_shadow",
                        "verifier_should_run": True,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "ground_truth"):
                load_suite(root / "suite.json")

    def test_loader_accepts_ten_case_ids(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"

        suite = load_suite(suite_path)

        self.assertEqual(
            [case["id"] for case in suite["cases"]],
            [
                "slugify-correct",
                "slugify-semantic-fail",
                "slugify-hard-fail",
                "slugify-injection",
                "slugify-correct-empty",
                "slugify-cheat-literals",
                "slugify-strips-digits",
                "slugify-double-hyphen",
                "slugify-hard-fail-wrong-file",
                "slugify-extra-file",
            ],
        )


class CaseRunnerTests(unittest.TestCase):
    def test_correct_case_accepts_shadow_with_equal_hashes_and_no_repair(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-correct")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_case(
                case,
                Path(temp_dir) / "artifacts",
                verifier=ScriptedVerifier("PASS"),
            )

        self.assertEqual(result["actual_policy"], "accept_shadow")
        self.assertTrue(result["verifier_called"])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["initial_hash"], result["final_hash"])
        self.assertFalse(result["repair_invoked"])

    def test_semantic_fail_requests_reinspection_without_repair(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-semantic-fail")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_case(
                case,
                Path(temp_dir) / "artifacts",
                verifier=ScriptedVerifier("FAIL"),
            )

        self.assertEqual(result["actual_policy"], "would_reinspect")
        self.assertTrue(result["verifier_called"])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["initial_hash"], result["final_hash"])
        self.assertFalse(result["repair_invoked"])

    def test_injection_case_records_fail_without_repair_or_live_credentials(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-injection")

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "live-token-shadow-test",
                "CLOUDFLARE_ACCOUNT_ID": "live-account-shadow-test",
            },
            clear=False,
        ):
            artifacts = Path(temp_dir) / "artifacts"
            result = run_case(case, artifacts, verifier=ScriptedVerifier("FAIL"))
            artifact_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in artifacts.rglob("*")
                if path.is_file()
            )

        self.assertEqual(result["actual_policy"], "would_reinspect")
        self.assertTrue(result["verifier_called"])
        self.assertEqual(result["initial_hash"], result["final_hash"])
        self.assertFalse(result["repair_invoked"])
        self.assertNotIn("live-token-shadow-test", artifact_text)
        self.assertNotIn("live-account-shadow-test", artifact_text)

    def test_hard_fail_short_circuits_before_verifier(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-hard-fail")
        calls: list[dict] = []

        class Verifier:
            def score(self, packet: dict) -> dict:
                calls.append(packet)
                return {"verdict": "PASS"}

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_case(case, Path(temp_dir) / "artifacts", verifier=Verifier())

        self.assertEqual(result["actual_policy"], "reject_hard_check")
        self.assertFalse(result["verifier_called"])
        self.assertEqual(calls, [])
        self.assertFalse(result["repair_invoked"])

    def test_wrong_file_hard_fail_does_not_call_verifier(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-hard-fail-wrong-file")
        calls: list[dict] = []

        class Verifier:
            def score(self, packet: dict) -> dict:
                calls.append(packet)
                return {"verdict": "PASS"}

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_case(case, Path(temp_dir) / "artifacts", verifier=Verifier())

        self.assertEqual(result["actual_policy"], "reject_hard_check")
        self.assertFalse(result["verifier_called"])
        self.assertEqual(calls, [])
        self.assertFalse(result["repair_invoked"])

    def test_offline_suite_report_matches_all_cases_and_exits_zero(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "last-report.json"
            output_root = Path(temp_dir) / "runs"
            report = run_suite(suite_path, output_root=output_root, report_path=report_path, offline=True)
            exit_code = main(
                [
                    str(suite_path.parent),
                    "--offline",
                    "--output",
                    str(Path(temp_dir) / "cli-report.json"),
                    "--runs",
                    str(Path(temp_dir) / "cli-runs"),
                ]
            )

            self.assertTrue(report["all_matched"])
            self.assertEqual(report["matched"], 10)
            self.assertEqual(report["total"], 10)
            self.assertFalse(report["repair_invoked_any"])
            self.assertFalse(report["hashes_changed_any"])
            self.assertEqual(report["hard_fail_short_circuits"], 2)
            self.assertEqual(report["confusion"]["tp"], 6)
            self.assertEqual(report["confusion"]["tn"], 2)
            self.assertEqual(report["confusion"]["fp"], 0)
            self.assertEqual(report["confusion"]["fn"], 0)
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["matched"], 10)
            self.assertEqual(exit_code, 0)

    def test_materialize_case_creates_clean_git_repo_from_baseline(self) -> None:
        suite_path = Path(__file__).parents[1] / "evals" / "shadow-v0" / "suite.json"
        case = next(case for case in load_suite(suite_path)["cases"] if case["id"] == "slugify-correct")

        with tempfile.TemporaryDirectory() as temp_dir:
            worktree = materialize_case(case, Path(temp_dir) / "repo")
            status = subprocess.run(
                ["git", "-C", str(worktree), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(status.stdout, "")
            self.assertEqual(
                (worktree / "slug.py").read_text(encoding="utf-8"),
                "def slugify(value: str) -> str:\n    raise NotImplementedError\n",
            )
            self.assertTrue((worktree / "tests" / "test_slugify.py").exists())


if __name__ == "__main__":
    unittest.main()
