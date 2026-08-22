from __future__ import annotations

import copy
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from shadow_orchestrator import (  # noqa: E402
    CloudflareVerifier,
    ManifestError,
    OrchestrationError,
    ProviderUnavailable,
    _build_evidence_packet,
    _canonical_json,
    _capture_candidate_bytes,
    _run_command,
    capture_candidate,
    main,
    normalize_cloudflare_response,
    post_json,
    run_manifest,
    validate_manifest,
)


def make_clean_run(root: Path, worker: list[str], hard_checks=None, criteria=None, risk_class: str = "low") -> Path:
    worktree = root / "repo"
    output_dir = root / "artifacts"
    subprocess.run(["git", "init", "-q", str(worktree)], check=True)
    subprocess.run(["git", "-C", str(worktree), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(worktree), "config", "user.name", "Test"], check=True)
    (worktree / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "baseline"], check=True)
    task_path = root / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "objective": "write a candidate",
                "risk_class": risk_class,
                "constraints": ["keep the change small"],
                "criteria": criteria
                or [{"id": "semantic-1", "text": "The candidate is valid.", "kind": "semantic"}],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "run-001",
                "task_spec": str(task_path),
                "worktree": str(worktree),
                "worker": {"command": worker, "timeout_seconds": 5},
                "hard_checks": hard_checks or [],
                "output_dir": str(output_dir),
                "provider": {},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


class ManifestValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "run_id": "run-001",
            "task_spec": "task.json",
            "worktree": "/tmp/worktree",
            "worker": {"command": ["python3", "worker.py"], "timeout_seconds": 30},
            "hard_checks": [],
            "output_dir": "/tmp/artifacts",
            "provider": {},
        }

    def test_rejects_shell_command_string(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["worker"]["command"] = "python3 worker.py"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_empty_worker_command(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["worker"]["command"] = []
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_empty_hard_check_command(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["hard_checks"] = [{"id": "check-1", "command": [], "timeout_seconds": 30}]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_shell_command_for_hard_check(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["hard_checks"] = [
            {"id": "check-1", "command": "python3 check.py", "timeout_seconds": 30}
        ]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_git_pathspec_magic_and_keeps_candidate_paths_literal(self) -> None:
        for path in (":", "*", "*.txt", "candidate?.txt", "[abc].txt", ".env", "safe/.env/token"):
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                manifest["candidate_paths"] = [path]
                with self.assertRaises(ManifestError):
                    validate_manifest(manifest)

    def test_normalizes_literal_candidate_paths(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["candidate_paths"] = ["./safe/./candidate.txt"]

        validated = validate_manifest(manifest)

        self.assertEqual(validated["candidate_paths"], ["safe/candidate.txt"])

    def test_rejects_candidate_path_traversal(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["candidate_paths"] = ["safe/../secret.txt"]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_non_positive_worker_timeout(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["worker"]["timeout_seconds"] = 0
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_invalid_evidence_byte_cap(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["evidence_byte_cap"] = 0
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)


class DotEnvBoundaryTests(unittest.TestCase):
    def test_manifest_named_dotenv_is_rejected_before_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / ".env"
            manifest_path.write_text("this is not JSON", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, r"\.env"):
                run_manifest(manifest_path)

    def test_task_spec_dotenv_is_rejected_before_loading_or_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "worker-ran.txt"
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                ],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            dotenv_path = root / ".env"
            dotenv_path.write_text("this is not a TaskSpec", encoding="utf-8")
            manifest["task_spec"] = ".env"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, r"task_spec.*\.env"):
                run_manifest(manifest_path)

            self.assertFalse(marker.exists())

    def test_worktree_and_output_dotenv_paths_are_rejected_before_worker(self) -> None:
        for field in ("worktree", "output_dir"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                marker = root / "worker-ran.txt"
                manifest_path = make_clean_run(
                    root,
                    [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                    ],
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest[field] = ".env"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                with self.assertRaisesRegex(ManifestError, rf"{field}.*\.env"):
                    run_manifest(manifest_path)

                self.assertFalse(marker.exists())


class BaselineTests(unittest.TestCase):
    def test_staged_only_dirty_baseline_is_rejected_before_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "worker-ran"
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"],
            )
            worktree = root / "repo"
            (worktree / "tracked.txt").write_text("preexisting staged change\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)

            result = run_manifest(manifest_path)

            self.assertEqual(result.policy_action, "reject_dirty_baseline")
            self.assertEqual(result.exit_code, 1)
            self.assertFalse(marker.exists())
            self.assertTrue(result.record["baseline"]["dirty"])
            self.assertGreater(result.record["baseline"]["diff_bytes"], 0)

    def test_nonempty_output_directory_is_rejected_before_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "worker-ran.txt"
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                ],
            )
            output_dir = root / "artifacts"
            output_dir.mkdir()
            (output_dir / "stale.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(ManifestError):
                run_manifest(manifest_path)

            self.assertFalse(marker.exists())
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["stale.json"],
            )

    def test_allowed_dirty_baseline_hash_includes_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(root, [sys.executable, "-c", "pass"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["allow_dirty_baseline"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            worktree = Path(manifest["worktree"])
            (worktree / "preexisting-untracked.txt").write_text("BASELINE", encoding="utf-8")

            class Verifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 1.0}

            result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.exit_code, 0)
            self.assertGreater(result.record["baseline"]["diff_bytes"], 0)
            self.assertEqual(
                result.record["baseline"]["diff_sha256"],
                result.record["candidate"]["diff_sha256"],
            )

    def test_dirty_baseline_fails_closed_before_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worktree = root / "repo"
            output_dir = root / "artifacts"
            subprocess.run(["git", "init", "-q", str(worktree)], check=True)
            subprocess.run(["git", "-C", str(worktree), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(worktree), "config", "user.name", "Test"], check=True)
            (worktree / "tracked.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "baseline"], check=True)
            (worktree / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            marker = worktree / "worker-ran.txt"
            task_path = root / "task.json"
            task_path.write_text(
                json.dumps(
                    {
                        "task_id": "task-001",
                        "objective": "write a candidate",
                        "risk_class": "low",
                        "criteria": [
                            {"id": "semantic-1", "text": "The candidate is valid.", "kind": "semantic"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": "dirty-run",
                        "task_spec": str(task_path),
                        "worktree": str(worktree),
                        "worker": {
                            "command": [
                                sys.executable,
                                "-c",
                                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                            ],
                            "timeout_seconds": 5,
                        },
                        "hard_checks": [],
                        "output_dir": str(output_dir),
                        "provider": {},
                    }
                ),
                encoding="utf-8",
            )

            result = run_manifest(manifest_path)

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.policy_action, "reject_dirty_baseline")
            self.assertFalse(marker.exists())
            record = json.loads((output_dir / "run-record.json").read_text(encoding="utf-8"))
            self.assertEqual(record["policy_action"], "reject_dirty_baseline")
            self.assertTrue(record["baseline"]["dirty"])


class WorkerExecutionTests(unittest.TestCase):
    def test_worker_and_hard_checks_do_not_receive_verifier_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [
                sys.executable,
                "-c",
                (
                    "import os; from pathlib import Path; "
                    "Path('worker-env.txt').write_text("
                    "str(os.getenv('CLOUDFLARE_API_TOKEN')) + '|' + "
                    "str(os.getenv('CLOUDFLARE_ACCOUNT_ID')), encoding='utf-8')"
                ),
            ]
            hard_checks = [
                {
                    "id": "credentials-isolated",
                    "command": [
                        sys.executable,
                        "-c",
                        (
                            "import os; "
                            "assert os.getenv('CLOUDFLARE_API_TOKEN') is None; "
                            "assert os.getenv('CLOUDFLARE_ACCOUNT_ID') is None"
                        ),
                    ],
                    "timeout_seconds": 5,
                }
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks)

            class Verifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 1.0}

            with patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_API_TOKEN": "verifier-secret-token",
                    "CLOUDFLARE_ACCOUNT_ID": "verifier-account-id",
                },
                clear=False,
            ):
                result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertEqual(
                (root / "repo" / "worker-env.txt").read_text(encoding="utf-8"),
                "None|None",
            )
            artifacts = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (root / "artifacts").rglob("*")
                if path.is_file()
            )
            self.assertNotIn("verifier-secret-token", artifacts)
            self.assertNotIn("verifier-account-id", artifacts)

    def test_worker_nonzero_stops_before_checks_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            check_marker = root / "check-ran.txt"
            worker = [sys.executable, "-c", "import sys; print('worker output'); sys.exit(7)"]
            hard_checks = [
                {
                    "id": "check-1",
                    "command": [sys.executable, "-c", f"from pathlib import Path; Path({str(check_marker)!r}).write_text('ran')"],
                    "timeout_seconds": 5,
                }
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks)
            calls: list[dict] = []

            class Verifier:
                def score(self, packet: dict) -> dict:
                    calls.append(packet)
                    return {}

            result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.policy_action, "worker_failed")
            self.assertFalse(check_marker.exists())
            self.assertEqual(calls, [])
            self.assertEqual(result.record["worker"]["returncode"], 7)
            self.assertEqual(result.record["worker"]["timed_out"], False)

    def test_worker_timeout_stops_before_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            check_marker = root / "check-ran.txt"
            worker = [sys.executable, "-c", "import time; time.sleep(2)"]
            hard_checks = [
                {
                    "id": "check-1",
                    "command": [sys.executable, "-c", f"from pathlib import Path; Path({str(check_marker)!r}).write_text('ran')"],
                    "timeout_seconds": 5,
                }
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["worker"]["timeout_seconds"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_manifest(manifest_path)

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.policy_action, "worker_timeout")
            self.assertFalse(check_marker.exists())
            self.assertTrue(result.record["worker"]["timed_out"])

    def test_worker_timeout_kills_a_sigterm_ignoring_descendant_and_keeps_capture_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "sigterm-ignoring-descendant-marker.txt"
            child = (
                "import signal, time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"time.sleep(2); Path({str(marker)!r}).write_text('late', encoding='utf-8')"
            )
            worker = [
                sys.executable,
                "-c",
                (
                    "import subprocess, sys, time; "
                    f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                    "from pathlib import Path; Path('candidate.txt').write_text('partial'); "
                    "time.sleep(5)"
                ),
            ]
            manifest_path = make_clean_run(root, worker)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["worker"]["timeout_seconds"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_manifest(manifest_path)
            candidate_before = (root / "artifacts" / "candidate.diff").read_bytes()
            time.sleep(2.5)
            candidate_after = (root / "artifacts" / "candidate.diff").read_bytes()

            self.assertEqual(result.policy_action, "worker_timeout")
            self.assertTrue(result.record["worker"]["timed_out"])
            self.assertFalse(marker.exists())
            self.assertEqual(candidate_before, candidate_after)
            self.assertEqual(hashlib.sha256(candidate_after).hexdigest(), result.record["final_candidate_hash"])

    def test_worker_timeout_kills_descendants_and_persists_partial_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "late-child-marker.txt"
            child = (
                "import time; from pathlib import Path; "
                f"time.sleep(1.5); Path({str(marker)!r}).write_text('late', encoding='utf-8')"
            )
            worker = [
                sys.executable,
                "-c",
                (
                    "import subprocess, sys, time; "
                    f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                    "from pathlib import Path; Path('candidate.txt').write_text('partial'); "
                    "time.sleep(3)"
                ),
            ]
            manifest_path = make_clean_run(root, worker)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["worker"]["timeout_seconds"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_manifest(manifest_path)
            time.sleep(2.0)

            self.assertEqual(result.policy_action, "worker_timeout")
            self.assertTrue(result.record["worker"]["timed_out"])
            self.assertFalse(marker.exists())
            self.assertTrue((root / "artifacts" / "candidate.diff").exists())
            self.assertTrue((root / "artifacts" / "candidate.json").exists())
            self.assertTrue(result.record["initial_candidate_hash"])
            self.assertTrue(result.record["final_candidate_hash"])

    def test_worker_nonzero_persists_partial_candidate_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('candidate.txt').write_text('partial'); raise SystemExit(7)",
            ]
            manifest_path = make_clean_run(root, worker)

            result = run_manifest(manifest_path)

            self.assertEqual(result.policy_action, "worker_failed")
            self.assertTrue((root / "artifacts" / "candidate.diff").exists())
            self.assertTrue((root / "artifacts" / "candidate.json").exists())
            self.assertTrue(result.record["initial_candidate_hash"])
            self.assertTrue(result.record["final_candidate_hash"])
            self.assertNotEqual(
                result.record["initial_candidate_hash"],
                result.record["final_candidate_hash"],
            )


class HardCheckTests(unittest.TestCase):
    def test_failed_hard_check_stops_before_verifier_and_records_a2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"]
            hard_checks = [
                {
                    "id": "check-fails",
                    "command": [sys.executable, "-c", "import sys; print('hard failure'); sys.exit(3)"],
                    "timeout_seconds": 5,
                },
                {
                    "id": "check-after",
                    "command": [sys.executable, "-c", "raise SystemExit('must not run')"],
                    "timeout_seconds": 5,
                },
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks)
            calls: list[dict] = []

            class Verifier:
                def score(self, packet: dict) -> dict:
                    calls.append(packet)
                    return {}

            result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.policy_action, "reject_hard_check")
            self.assertEqual(calls, [])
            self.assertEqual(len(result.record["hard_checks"]), 1)
            self.assertEqual(result.record["hard_checks"][0]["authority"], "A2")
            self.assertEqual(result.record["hard_checks"][0]["returncode"], 3)

    def test_failed_hard_check_persists_partial_candidate_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('candidate.txt').write_text('worker')",
            ]
            hard_checks = [
                {
                    "id": "check-mutates-and-fails",
                    "command": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('candidate.txt').write_text('check'); raise SystemExit(3)",
                    ],
                    "timeout_seconds": 5,
                }
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks)

            result = run_manifest(manifest_path)

            self.assertEqual(result.policy_action, "reject_hard_check")
            self.assertEqual(result.record["hard_checks"][0]["returncode"], 3)
            self.assertTrue((root / "artifacts" / "candidate.diff").exists())
            self.assertTrue((root / "artifacts" / "candidate.json").exists())
            self.assertTrue(result.record["initial_candidate_hash"])
            self.assertTrue(result.record["final_candidate_hash"])
            self.assertNotEqual(
                result.record["initial_candidate_hash"],
                result.record["final_candidate_hash"],
            )


class TaskSpecCrossValidationTests(unittest.TestCase):
    def test_hard_task_criterion_requires_manifest_hard_check_before_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "worker-ran.txt"
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                ],
                criteria=[{"id": "H1", "text": "hard", "kind": "hard"}],
            )

            with self.assertRaisesRegex(ManifestError, "hard criterion"):
                run_manifest(manifest_path)

            self.assertFalse(marker.exists())


class EvidencePacketTests(unittest.TestCase):
    def test_large_diff_never_attempts_oversized_packet_serialization(self) -> None:
        observed_sizes: list[int] = []

        def observe(value: object) -> bytes:
            encoded = _canonical_json(value)
            observed_sizes.append(len(encoded))
            return encoded

        with patch("shadow_orchestrator._canonical_json", side_effect=observe):
            packet = _build_evidence_packet(
                {"id": "C1", "text": "small criterion", "kind": "semantic"},
                ["small constraint"],
                b"A" * 1_000_000,
                [{"id": "check", "passed": True}],
                512,
            )

        self.assertLessEqual(len(_canonical_json(packet)), 512)
        self.assertLessEqual(max(observed_sizes), 1024)

    def test_mixed_case_authorization_is_redacted_and_packet_hash_matches_persisted_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('candidate.txt').write_text('aUtHoRiZaTiOn: forbidden')",
                ],
            )
            seen_packets: list[dict] = []

            class Verifier:
                def score(self, packet: dict) -> dict:
                    seen_packets.append(copy.deepcopy(packet))
                    return {"verdict": "PASS", "normalized_score": 1.0}

            result = run_manifest(manifest_path, verifier=Verifier())
            artifacts = root / "artifacts"
            candidate_text = (artifacts / "candidate.diff").read_text(encoding="utf-8", errors="replace")
            persisted = json.loads((artifacts / "evidence-packets.json").read_text(encoding="utf-8"))

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertNotIn("authorization", candidate_text.casefold())
            self.assertEqual(len(seen_packets), 1)
            self.assertEqual(len(persisted), 1)
            packet_record = dict(persisted[0])
            expected_hash = packet_record.pop("packet_sha256")
            self.assertEqual(hashlib.sha256(_canonical_json(packet_record)).hexdigest(), expected_hash)
            self.assertEqual(packet_record, seen_packets[0])

    def test_passing_worker_and_checks_persist_complete_diff_and_semantic_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('VERIFIED')"]
            hard_checks = [
                {
                    "id": "candidate-exists",
                    "command": [sys.executable, "-c", "from pathlib import Path; assert Path('candidate.txt').read_text() == 'VERIFIED'"],
                    "timeout_seconds": 5,
                }
            ]
            criteria = [
                {"id": "semantic-1", "text": "The candidate contains VERIFIED.", "kind": "semantic"},
                {"id": "semantic-2", "text": "The candidate is small.", "kind": "semantic"},
                {"id": "hard-in-task", "text": "A hard fact.", "kind": "hard"},
            ]
            manifest_path = make_clean_run(root, worker, hard_checks=hard_checks, criteria=criteria)
            packets: list[dict] = []

            class Verifier:
                def score(self, packet: dict) -> dict:
                    packets.append(packet)
                    return {
                        "verdict": "PASS",
                        "normalized_score": 1.0,
                        "entropy": 0.0,
                        "margin": 1.0,
                        "raw_logprobs": {"PASS": -0.01, "FAIL": -5.0},
                    }

            result = run_manifest(manifest_path, verifier=Verifier())
            output_dir = root / "artifacts"
            diff = (output_dir / "candidate.diff").read_text(encoding="utf-8")

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertIn("candidate.txt", diff)
            self.assertIn("VERIFIED", diff)
            self.assertEqual(len(packets), 2)
            self.assertEqual({packet["criterion"]["id"] for packet in packets}, {"semantic-1", "semantic-2"})
            for packet in packets:
                self.assertIn("constraints", packet)
                self.assertIn("candidate_diff_excerpt", packet)
                self.assertIn("deterministic_checks", packet)
                self.assertNotIn("worker output", json.dumps(packet))
            self.assertEqual(len(result.record["evidence_packets"]), 2)
            self.assertEqual(result.record["candidate"]["diff_sha256"], result.record["final_candidate_hash"])
            self.assertEqual(result.record["initial_candidate_hash"], result.record["final_candidate_hash"])

    def test_complete_canonical_evidence_packet_respects_byte_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cap = 512
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('candidate.txt').write_text('é' * 300)",
            ]
            criteria = [
                {
                    "id": "semantic-1",
                    "text": "The candidate is valid and UTF-8 safe.",
                    "kind": "semantic",
                    "evidence_required": ["candidate diff"],
                }
            ]
            manifest_path = make_clean_run(root, worker, criteria=criteria)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence_byte_cap"] = cap
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            packets: list[dict] = []

            class Verifier:
                def score(self, packet: dict) -> dict:
                    packets.append(packet)
                    return {"verdict": "PASS", "normalized_score": 1.0}

            result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertEqual(len(packets), 1)
            self.assertLessEqual(len(_canonical_json(packets[0])), cap)
            self.assertIn("[output truncated]", packets[0]["candidate_diff_excerpt"])

    def test_fixed_evidence_metadata_over_cap_fails_closed_before_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "verifier-called.txt"
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('candidate.txt').write_text('candidate')",
            ]
            criteria = [{"id": "semantic-1", "text": "x" * 2000, "kind": "semantic"}]
            manifest_path = make_clean_run(root, worker, criteria=criteria)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence_byte_cap"] = 256
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            class Verifier:
                def score(self, packet: dict) -> dict:
                    marker.write_text("called", encoding="utf-8")
                    return {"verdict": "PASS", "normalized_score": 1.0}

            result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.policy_action, "evidence_cap_exceeded")
            self.assertIn("fixed evidence metadata", result.record["error"])
            self.assertFalse(marker.exists())


class HardCapTests(unittest.TestCase):
    def test_post_json_rejects_body_over_configured_cap_before_decode(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                self.last_size = size
                return b"abcd"

        response = Response()
        with patch("shadow_orchestrator._CLOUDFLARE_OPENER.open", return_value=response):
            with self.assertRaisesRegex(ProviderUnavailable, "exceeded"):
                post_json("https://example.invalid", {}, {}, timeout=1, response_cap=3)

        self.assertEqual(response.last_size, 4)

    def test_subprocess_output_never_exceeds_output_cap(self) -> None:
        result = _run_command(
            [sys.executable, "-c", "print('x' * 1000)"],
            Path.cwd(),
            timeout=5,
            output_cap=32,
        )

        self.assertLessEqual(len(result["stdout"].encode("utf-8")), 32)
        self.assertIn("truncated", result["stdout"])


class CandidateCaptureTests(unittest.TestCase):
    def test_staged_only_content_appears_in_read_only_layered_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(root, [sys.executable, "-c", "pass"])
            worktree = root / "repo"
            (worktree / "tracked.txt").write_text("STAGED-ONLY\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)

            snapshot = capture_candidate(worktree)

            self.assertIn("--- BEGIN STAGED (HEAD -> INDEX) ---", snapshot["diff"])
            self.assertIn("STAGED-ONLY", snapshot["diff"])
            self.assertIn("--- BEGIN UNSTAGED (INDEX -> WORKTREE) ---", snapshot["diff"])
            self.assertIn("--- BEGIN UNTRACKED (WORKTREE ONLY) ---", snapshot["diff"])
            self.assertNotIn("git add", manifest_path.read_text(encoding="utf-8"))

    def test_staged_and_independently_unstaged_content_both_appear(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_clean_run(root, [sys.executable, "-c", "pass"])
            worktree = root / "repo"
            (worktree / "tracked.txt").write_text("STAGED-VALUE\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)
            (worktree / "tracked.txt").write_text("UNSTAGED-VALUE\n", encoding="utf-8")

            snapshot = capture_candidate(worktree)

            self.assertIn("STAGED-VALUE", snapshot["diff"])
            self.assertIn("UNSTAGED-VALUE", snapshot["diff"])
            self.assertLess(
                snapshot["diff"].index("--- BEGIN STAGED (HEAD -> INDEX) ---"),
                snapshot["diff"].index("--- BEGIN UNSTAGED (INDEX -> WORKTREE) ---"),
            )

    def test_untracked_text_and_binary_files_appear_in_layered_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_clean_run(root, [sys.executable, "-c", "pass"])
            worktree = root / "repo"
            (worktree / "untracked-text.txt").write_text("UNTRACKED-TEXT\n", encoding="utf-8")
            (worktree / "untracked-binary.bin").write_bytes(bytes([0, 255, 1]) + b"binary")

            diff = _capture_candidate_bytes(worktree)

            self.assertIn(b"untracked-text.txt", diff)
            self.assertIn(b"UNTRACKED-TEXT", diff)
            self.assertIn(b"untracked-binary.bin", diff)
            self.assertIn(b"GIT binary patch", diff)

    def test_layered_capture_preserves_objects_index_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_clean_run(root, [sys.executable, "-c", "pass"])
            worktree = root / "repo"
            (worktree / "tracked.txt").write_text("STAGED\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "tracked.txt"], check=True)
            (worktree / "tracked.txt").write_text("UNSTAGED\n", encoding="utf-8")
            (worktree / "untracked.txt").write_text("UNTRACKED\n", encoding="utf-8")

            def object_inventory() -> dict[str, str]:
                objects_root = worktree / ".git" / "objects"
                return {
                    str(path.relative_to(objects_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in objects_root.rglob("*")
                    if path.is_file()
                }

            status_command = ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"]
            status_before = subprocess.run(status_command, check=True, stdout=subprocess.PIPE, text=True).stdout
            index_before = (worktree / ".git" / "index").read_bytes()
            objects_before = object_inventory()

            _capture_candidate_bytes(worktree)

            status_after = subprocess.run(status_command, check=True, stdout=subprocess.PIPE, text=True).stdout
            self.assertEqual(index_before, (worktree / ".git" / "index").read_bytes())
            self.assertEqual(status_before, status_after)
            self.assertEqual(objects_before, object_inventory())

    def test_untracked_candidate_is_captured_without_mutating_real_index_or_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('untracked-candidate.txt').write_text('UNTRACKED', encoding='utf-8')",
            ]
            manifest_path = make_clean_run(root, worker)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["candidate_paths"] = ["untracked-candidate.txt"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            worktree = Path(manifest["worktree"])
            index_before = (worktree / ".git" / "index").read_bytes()

            class Verifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 1.0, "entropy": 0.0, "margin": 1.0}

            result = run_manifest(manifest_path, verifier=Verifier())
            output_dir = root / "artifacts"
            diff_bytes = (output_dir / "candidate.diff").read_bytes()
            status_after = subprocess.run(
                ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertIn(b"untracked-candidate.txt", diff_bytes)
            self.assertIn(b"UNTRACKED", diff_bytes)
            self.assertEqual(hashlib.sha256(diff_bytes).hexdigest(), result.record["candidate"]["diff_sha256"])
            self.assertEqual(index_before, (worktree / ".git" / "index").read_bytes())
            self.assertEqual(status_after, "?? untracked-candidate.txt\n")
            staged = subprocess.run(
                ["git", "-C", str(worktree), "diff", "--cached", "--name-only"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout
            self.assertEqual(staged, "")
    def test_candidate_paths_limit_diff_without_staging_other_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worker = [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('selected.txt').write_text('SELECTED'); Path('other.txt').write_text('OTHER')",
            ]
            manifest_path = make_clean_run(root, worker)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["candidate_paths"] = ["selected.txt"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            class Verifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 1.0, "entropy": 0.0, "margin": 1.0}

            run_manifest(manifest_path, verifier=Verifier())
            diff = (root / "artifacts" / "candidate.diff").read_text(encoding="utf-8")

            self.assertIn("selected.txt", diff)
            self.assertIn("SELECTED", diff)
            self.assertNotIn("other.txt", diff)
            self.assertNotIn("OTHER", diff)


class CandidateCaptureSecurityTests(unittest.TestCase):
    def test_staged_baseline_preflights_filters_before_content_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            marker = root / "filter-marker"
            worker_marker = root / "worker-marker"
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", f"from pathlib import Path; Path({str(worker_marker)!r}).write_text('ran')"],
            )
            worktree = root / "repo"
            filter_script = root / "filter.py"
            filter_script.write_text(
                "import os, pathlib, sys\n"
                f"pathlib.Path({str(marker)!r}).write_text(os.environ.get('CLOUDFLARE_API_TOKEN', 'missing'))\n"
                "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(worktree), "config", "filter.spy.clean", f"{sys.executable} {filter_script}"],
                check=True,
            )
            (worktree / ".gitattributes").write_text("tracked.txt filter=spy\n", encoding="utf-8")
            (worktree / "tracked.txt").write_text("staged baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", ".gitattributes", "tracked.txt"], check=True)
            marker.unlink(missing_ok=True)

            result = run_manifest(manifest_path)

            self.assertEqual(result.policy_action, "baseline_inspection_failed")
            self.assertFalse(marker.exists())
            self.assertFalse(worker_marker.exists())

    def test_active_clean_filter_is_rejected_before_it_can_observe_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('candidate.txt').write_text('changed', encoding='utf-8')",
                ],
            )
            worktree = root / "repo"
            (worktree / "candidate.txt").write_text("baseline", encoding="utf-8")
            (worktree / ".gitattributes").write_text("candidate.txt filter=credential-leak\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(worktree), "add", "candidate.txt", ".gitattributes"], check=True)
            subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "filtered baseline"], check=True)

            marker = root / "filter-observed.txt"
            filter_program = root / "clean-filter.py"
            filter_program.write_text(
                "import os; from pathlib import Path; import sys; "
                f"Path({str(marker)!r}).write_text(os.environ.get('CLOUDFLARE_API_TOKEN', 'missing')); "
                "sys.stdout.write(sys.stdin.read())",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "config",
                    "filter.credential-leak.clean",
                    f"{sys.executable} {filter_program}",
                ],
                check=True,
            )

            class Verifier:
                def score(self, packet: dict) -> dict:
                    raise AssertionError("verifier must not run after capture rejection")

            with patch.dict(
                os.environ,
                {"CLOUDFLARE_API_TOKEN": "verifier-secret-token", "CLOUDFLARE_ACCOUNT_ID": "verifier-account"},
                clear=False,
            ):
                result = run_manifest(manifest_path, verifier=Verifier())

            self.assertEqual(result.policy_action, "candidate_capture_failed")
            self.assertIn("filter", result.record["error"].lower())
            self.assertFalse(marker.exists())


class CloudflareScoringTests(unittest.TestCase):
    @staticmethod
    def response(verdict: str = "PASS") -> dict:
        return {
            "id": "fake-response",
            "usage": {"prompt_tokens": 31, "completion_tokens": 1},
            "choices": [
                {
                    "message": {"content": verdict},
                    "logprobs": {
                        "content": [
                            {
                                "token": verdict,
                                "bytes": list(verdict.encode("utf-8")),
                                "logprob": -0.1,
                                "top_logprobs": [
                                    {"token": "ignored", "bytes": [80, 65, 83, 83], "logprob": -0.1},
                                    {"token": "ignored", "bytes": [70, 65, 73, 76], "logprob": -2.1},
                                ],
                            }
                        ]
                    },
                }
            ],
        }

    def test_normalizer_decodes_byte_labels_and_calculates_binary_metrics(self) -> None:
        result = normalize_cloudflare_response(self.response())

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(set(result["raw_logprobs"]), {"PASS", "FAIL"})
        self.assertGreater(result["normalized_score"], 0.5)
        self.assertGreaterEqual(result["entropy"], 0.0)
        self.assertGreater(result["margin"], 0.0)

    def test_cloudflare_request_disables_thinking_and_uses_fixed_environment_endpoint(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"CLOUDFLARE_ACCOUNT_ID": "fake-account", "CLOUDFLARE_API_TOKEN": "fake-token"},
                clear=True,
            ),
            patch("shadow_orchestrator.post_json", return_value=self.response()) as post_json,
        ):
            result = CloudflareVerifier({"model": "fake-model"}).score(
                {"criterion": {"id": "C1", "text": "valid", "kind": "semantic"}}
            )

        self.assertEqual(
            post_json.call_args.args[0],
            "https://api.cloudflare.com/client/v4/accounts/fake-account/ai/v1/chat/completions",
        )
        payload = post_json.call_args.args[2]
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(result["verdict"], "PASS")
        self.assertNotIn("Authorization", json.dumps(result["raw_response"]))

    def test_cloudflare_transport_does_not_follow_redirects_or_forward_authorization(self) -> None:
        first_requests: list[dict[str, str]] = []
        second_requests: list[dict[str, str]] = []

        class SecondHandler(http.server.BaseHTTPRequestHandler):
            def _respond(self) -> None:
                second_requests.append({key: value for key, value in self.headers.items()})
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def do_GET(self) -> None:  # noqa: N802
                self._respond()

            def do_POST(self) -> None:  # noqa: N802
                self._respond()

            def log_message(self, format: str, *args: object) -> None:
                return

        second_server = http.server.HTTPServer(("127.0.0.1", 0), SecondHandler)

        class FirstHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                first_requests.append({key: value for key, value in self.headers.items()})
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{second_server.server_port}/second")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        first_server = http.server.HTTPServer(("127.0.0.1", 0), FirstHandler)
        servers = (first_server, second_server)
        threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in servers
        ]
        for thread in threads:
            thread.start()
        try:
            with self.assertRaisesRegex(ProviderUnavailable, "Cloudflare HTTP 302"):
                post_json(
                    f"http://127.0.0.1:{first_server.server_port}/start",
                    {"Authorization": "Bearer redirect-secret"},
                    {},
                    timeout=2,
                )
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)

        self.assertEqual(len(first_requests), 1)
        self.assertEqual(second_requests, [])
        self.assertEqual(first_requests[0].get("Authorization"), "Bearer redirect-secret")

    def test_cloudflare_account_id_cannot_inject_path_or_query(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_ACCOUNT_ID": "safe/../../other-account?redirect=1",
                    "CLOUDFLARE_API_TOKEN": "fake-token",
                },
                clear=True,
            ),
            patch("shadow_orchestrator.post_json", return_value=self.response()) as post_json,
        ):
            with self.assertRaises(ProviderUnavailable):
                CloudflareVerifier().score({"criterion": {"id": "C1"}})

        post_json.assert_not_called()


class ProviderManifestBoundaryTests(unittest.TestCase):
    def test_schema_matches_fixed_provider_boundary(self) -> None:
        schema_path = Path(__file__).parents[1] / "schemas" / "shadow-manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        provider = schema["properties"]["provider"]

        self.assertFalse(provider["additionalProperties"])
        self.assertNotIn("endpoint", provider["properties"])
        self.assertNotIn("headers", provider["properties"])
        self.assertIn("response_byte_cap", provider["properties"])
        self.assertEqual(schema["$defs"]["argv"]["items"].get("minLength"), 1)
        task_schema_path = Path(__file__).parents[1] / "schemas" / "task-spec.schema.json"
        task_schema = json.loads(task_schema_path.read_text(encoding="utf-8"))
        self.assertEqual(task_schema["properties"]["criteria"].get("minItems"), 1)
        self.assertEqual(task_schema["properties"]["task_id"].get("minLength"), 1)
        self.assertEqual(task_schema["properties"]["objective"].get("minLength"), 1)
        run_schema_path = Path(__file__).parents[1] / "schemas" / "run-record.schema.json"
        run_schema = json.loads(run_schema_path.read_text(encoding="utf-8"))
        self.assertIn("evidence_cap_exceeded", run_schema["properties"]["policy_action"]["enum"])

    def test_rejects_endpoint_and_unknown_provider_fields_before_worker_execution(self) -> None:
        for provider_field in ("endpoint", "headers", "api_token"):
            with self.subTest(provider_field=provider_field), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                marker = root / "worker-ran.txt"
                manifest_path = make_clean_run(
                    root,
                    [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                    ],
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["provider"] = {provider_field: "https://example.invalid"}
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                with self.assertRaises(ManifestError):
                    run_manifest(manifest_path)

                self.assertFalse(marker.exists())


class PolicyAndCliTests(unittest.TestCase):
    def test_unusable_provider_falls_back_by_risk_without_repair(self) -> None:
        for risk_class, expected_action, expected_exit in (
            ("low", "accept_deterministic_fallback", 0),
            ("medium", "accept_deterministic_fallback", 0),
            ("high", "manual_escalation", 1),
        ):
            with self.subTest(risk_class=risk_class), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                marker = root / "repair-ran.txt"
                manifest_path = make_clean_run(
                    root,
                    [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
                    risk_class=risk_class,
                )

                class UnusableVerifier:
                    def score(self, packet: dict) -> dict:
                        return {"verdict": "MAYBE"}

                result = run_manifest(manifest_path, verifier=UnusableVerifier())

                self.assertEqual(result.policy_action, expected_action)
                self.assertEqual(result.exit_code, expected_exit)
                self.assertFalse(marker.exists())
                self.assertTrue((root / "repo" / "candidate.txt").exists())

    def test_verifier_fail_requests_reinspection_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )

            class FailingVerifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "FAIL", "normalized_score": 0.0, "entropy": 0.0, "margin": 1.0}

            result = run_manifest(manifest_path, verifier=FailingVerifier())

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.policy_action, "would_reinspect")
            self.assertEqual(result.record["final_outcome"], "fail")
            self.assertFalse(result.record["repair_invoked"])
            instruction = root / "artifacts" / "reinspect-instruction.md"
            self.assertTrue(instruction.is_file())
            text = instruction.read_text(encoding="utf-8")
            self.assertIn("Do not apply", text)
            self.assertIn("semantic-1", text)
            self.assertFalse(result.record.get("stage1", {}).get("applied", True))
            self.assertGreater(result.record["stage1"]["instruction_bytes"], 0)
            self.assertEqual(
                result.record["initial_candidate_hash"],
                result.record["final_candidate_hash"],
            )

    def test_accept_shadow_does_not_write_reinspect_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )

            class PassingVerifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 0.97, "entropy": 0.13, "margin": 0.94}

            result = run_manifest(manifest_path, verifier=PassingVerifier())

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertFalse((root / "artifacts" / "reinspect-instruction.md").exists())
            self.assertFalse(result.record.get("stage1", {}).get("instruction_written", False))

    def test_low_score_pass_requests_reinspection_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )

            class UncertainVerifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 0.73, "entropy": 0.58, "margin": 0.46}

            result = run_manifest(manifest_path, verifier=UncertainVerifier())

            self.assertEqual(result.policy_action, "would_reinspect")
            self.assertEqual(result.record["final_outcome"], "fail")
            self.assertFalse(result.record["repair_invoked"])
            self.assertIn("confidence", result.record["policy_reason"])

    def test_high_entropy_pass_requests_reinspection_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )

            class HighEntropyVerifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 0.95, "entropy": 0.50, "margin": 0.90}

            result = run_manifest(manifest_path, verifier=HighEntropyVerifier())

            self.assertEqual(result.policy_action, "would_reinspect")
            self.assertFalse(result.record["repair_invoked"])

    def test_high_confidence_pass_still_accepts_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )

            class ConfidentVerifier:
                def score(self, packet: dict) -> dict:
                    return {"verdict": "PASS", "normalized_score": 0.97, "entropy": 0.13, "margin": 0.94}

            result = run_manifest(manifest_path, verifier=ConfidentVerifier())

            self.assertEqual(result.policy_action, "accept_shadow")
            self.assertEqual(result.record["final_outcome"], "pass")
            self.assertFalse(result.record["repair_invoked"])

    def test_confirmed_fail_precedes_later_provider_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            criteria = [
                {"id": "semantic-1", "text": "first", "kind": "semantic"},
                {"id": "semantic-2", "text": "second", "kind": "semantic"},
            ]
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
                criteria=criteria,
            )
            calls = 0

            class PartiallyUnavailableVerifier:
                def score(self, packet: dict) -> dict:
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return {"verdict": "FAIL", "normalized_score": 0.0}
                    raise ProviderUnavailable("provider unavailable after first criterion")

            result = run_manifest(manifest_path, verifier=PartiallyUnavailableVerifier())

            self.assertEqual(calls, 2)
            self.assertEqual(result.policy_action, "would_reinspect")
            self.assertEqual(result.record["final_outcome"], "fail")
            self.assertEqual(len(result.record["verifier_results"]), 1)
            self.assertIn("provider unavailable", result.record["provider_errors"][0])

    def test_unusable_cloudflare_response_is_saved_without_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )
            response = CloudflareScoringTests.response()
            response["headers"] = {"Authorization": "Bearer fake-token"}
            response["choices"][0]["logprobs"]["content"][0]["top_logprobs"] = [
                response["choices"][0]["logprobs"]["content"][0]["top_logprobs"][0]
            ]
            with (
                patch.dict(
                    os.environ,
                    {"CLOUDFLARE_ACCOUNT_ID": "fake-account", "CLOUDFLARE_API_TOKEN": "fake-token"},
                    clear=True,
                ),
                patch("shadow_orchestrator.post_json", return_value=response),
            ):
                result = run_manifest(
                    manifest_path,
                    verifier=CloudflareVerifier({"model": "fake-model"}),
                )

            raw_files = sorted((root / "artifacts").glob("provider-response-*.json"))
            self.assertEqual(result.policy_action, "accept_deterministic_fallback")
            self.assertEqual(len(raw_files), 1)
            raw_text = raw_files[0].read_text(encoding="utf-8")
            self.assertNotIn("Authorization", raw_text)
            self.assertNotIn("fake-token", raw_text)

    def test_artifacts_never_persist_environment_credentials_or_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
            )
            response = CloudflareScoringTests.response()
            with (
                patch.dict(
                    os.environ,
                    {"CLOUDFLARE_ACCOUNT_ID": "fake-account", "CLOUDFLARE_API_TOKEN": "fake-token"},
                    clear=True,
                ),
                patch("shadow_orchestrator.post_json", return_value=response),
            ):
                result = run_manifest(
                    manifest_path,
                    verifier=CloudflareVerifier({"model": "fake-model"}),
                )

            self.assertEqual(result.exit_code, 0)
            for artifact in (root / "artifacts").rglob("*.json"):
                text = artifact.read_text(encoding="utf-8")
                self.assertNotIn("fake-token", text, str(artifact))
                self.assertNotIn("Authorization", text, str(artifact))

    def test_embedded_credentials_are_redacted_from_every_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            token = "embedded-secret-token"
            account = "embedded-account-id"
            manifest_path = make_clean_run(
                root,
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; import sys; "
                        f"print('Authorization: Bearer {token}'); "
                        f"Path('candidate.txt').write_text('Authorization: Bearer {token} {account}', encoding='utf-8')"
                    ),
                ],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            task = json.loads((root / "task.json").read_text(encoding="utf-8"))
            task["constraints"] = [f"Bearer {token}", account]
            (root / "task.json").write_text(json.dumps(task), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            class EmbeddedSecretVerifier:
                def score(self, packet: dict) -> dict:
                    return {
                        "verdict": "PASS",
                        "normalized_score": 1.0,
                        "usage": {"detail": f"Authorization: Bearer {token} {account}"},
                        "raw_response": {
                            "Authorization": f"Bearer {token}",
                            "nested": [f"prefix-{token}-suffix", account],
                        },
                    }

            with patch.dict(
                os.environ,
                {"CLOUDFLARE_ACCOUNT_ID": account, "CLOUDFLARE_API_TOKEN": token},
                clear=True,
            ):
                result = run_manifest(manifest_path, verifier=EmbeddedSecretVerifier())

            self.assertEqual(result.policy_action, "accept_shadow")
            for artifact in (root / "artifacts").rglob("*"):
                if artifact.is_file():
                    text = artifact.read_text(encoding="utf-8", errors="replace")
                    self.assertNotIn(token, text, str(artifact))
                    self.assertNotIn(account, text, str(artifact))
                    self.assertNotIn("Authorization", text, str(artifact))

    def test_cli_returns_nonzero_for_high_risk_manual_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = make_clean_run(
                root,
                [sys.executable, "-c", "from pathlib import Path; Path('candidate.txt').write_text('candidate')"],
                risk_class="high",
            )

            class UnusableVerifier:
                def score(self, packet: dict) -> dict:
                    return {}

            with patch("shadow_orchestrator.CloudflareVerifier", return_value=UnusableVerifier()):
                self.assertEqual(main([str(manifest_path)]), 1)


if __name__ == "__main__":
    unittest.main()
